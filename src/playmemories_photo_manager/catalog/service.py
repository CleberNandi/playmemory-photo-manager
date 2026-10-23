"""Catalog application use cases and transaction boundaries."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import PurePosixPath

from .errors import (
    DuplicateAssociationError,
    InvalidInputError,
    InvalidReferenceError,
    InvariantViolationError,
    NotFoundError,
    PersistenceError,
    UniquenessConflictError,
)
from .models import (
    Album,
    Annotation,
    Asset,
    AssetKind,
    EntryType,
    FileLocation,
    HashState,
    LibraryRoot,
    LocationAvailability,
    RootAvailability,
    Tag,
)
from .repository import CatalogRepository
from .tags import normalize_tag

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


class Catalog:
    """Application facade over one managed, caller-owned SQLite connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        try:
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            functions_available = connection.execute(
                "SELECT is_uuid('00000000-0000-0000-0000-000000000000'), normalize_tag(' X ')"
            ).fetchone()
        except sqlite3.DatabaseError as error:
            raise InvalidInputError("catalog requires a managed connection") from error
        if foreign_keys != 1 or tuple(functions_available) != (1, "x"):
            raise InvalidInputError("catalog requires a managed connection with foreign keys")
        self._connection = connection
        self._repository = CatalogRepository(connection)

    def create_asset(
        self,
        kind: AssetKind | str,
        *,
        sha256: str | None = None,
        hash_state: HashState | str = HashState.ABSENT,
        byte_size: int | None = None,
        media_type: str | None = None,
    ) -> Asset:
        kind = _enum(AssetKind, kind, "kind")
        hash_state = _enum(HashState, hash_state, "hash_state")
        if byte_size is not None and (
            isinstance(byte_size, bool) or not isinstance(byte_size, int) or byte_size < 0
        ):
            raise InvalidInputError("byte_size must be a non-negative integer")
        if media_type is not None and not isinstance(media_type, str):
            raise InvalidInputError("media_type must be a string or null")
        if sha256 is None and hash_state is not HashState.ABSENT:
            raise InvalidInputError("hash_state must be absent when sha256 is omitted")
        if sha256 is not None:
            if len(sha256) != 64 or any(
                character not in "0123456789abcdef" for character in sha256
            ):
                raise InvalidInputError("sha256 must be 64 lowercase hexadecimal characters")
            if hash_state is HashState.ABSENT:
                raise InvalidInputError("hash_state cannot be absent when sha256 is supplied")
            if hash_state is HashState.VERIFIED:
                raise InvalidInputError(
                    "verified hashes require a future evidence-aware verification operation"
                )
        identifier = str(uuid.uuid4())
        with self._write():
            self._repository.insert_asset(
                identifier, kind, sha256, hash_state, byte_size, media_type
            )
        return self.get_asset(identifier)

    def get_asset(self, asset_id: str) -> Asset:
        _uuid(asset_id, "asset_id")
        asset = self._read(self._repository.get_asset, asset_id)
        if asset is None:
            raise NotFoundError("asset does not exist")
        return asset

    def list_assets(self, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> list[Asset]:
        return self._read(self._repository.list_assets, *_page(limit, offset))

    def get_asset_locations(
        self, asset_id: str, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
    ) -> list[FileLocation]:
        self.get_asset(asset_id)
        return self._read(self._repository.list_asset_locations, asset_id, *_page(limit, offset))

    def register_root(
        self,
        display_name: str,
        normalized_path: str,
        *,
        availability: RootAvailability | str = RootAvailability.AVAILABLE,
    ) -> LibraryRoot:
        display_name = _nonblank(display_name, "display_name")
        normalized_path = _nonblank(normalized_path, "normalized_path")
        availability = _enum(RootAvailability, availability, "availability")
        identifier = str(uuid.uuid4())
        with self._write():
            try:
                self._repository.insert_root(
                    identifier, display_name, normalized_path, availability
                )
            except sqlite3.IntegrityError as error:
                raise UniquenessConflictError("library root path already exists") from error
        return self.get_root(identifier)

    def get_root(self, root_id: str) -> LibraryRoot:
        _uuid(root_id, "root_id")
        root = self._read(self._repository.get_root, root_id)
        if root is None:
            raise NotFoundError("library root does not exist")
        return root

    def list_roots(self, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> list[LibraryRoot]:
        return self._read(self._repository.list_roots, *_page(limit, offset))

    def register_location(
        self,
        asset_id: str,
        root_id: str,
        relative_path: str,
        *,
        last_seen_at: str,
        availability: LocationAvailability | str = LocationAvailability.PRESENT,
        entry_type: EntryType | str = EntryType.FILE,
        symlink_target: str | None = None,
        filesystem_id: str | None = None,
        observed_byte_size: int | None = None,
        observed_mtime_ns: int | None = None,
    ) -> FileLocation:
        _uuid(asset_id, "asset_id")
        _uuid(root_id, "root_id")
        relative_path = _relative_path(relative_path)
        last_seen_at = _nonblank(last_seen_at, "last_seen_at")
        availability = _enum(LocationAvailability, availability, "availability")
        entry_type = _enum(EntryType, entry_type, "entry_type")
        if availability in {
            LocationAvailability.MISSING,
            LocationAvailability.MOVED_CANDIDATE,
        }:
            raise InvalidInputError(
                "missing and moved_candidate require a future evidence-aware transition"
            )
        if (entry_type is EntryType.SYMLINK) != (symlink_target is not None):
            raise InvalidInputError("symlink_target is required only for symlink entries")
        for name, value in (
            ("observed_byte_size", observed_byte_size),
            ("observed_mtime_ns", observed_mtime_ns),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise InvalidInputError(f"{name} must be a non-negative integer")
        location = FileLocation(
            id=str(uuid.uuid4()),
            asset_id=asset_id,
            library_root_id=root_id,
            normalized_relative_path=relative_path,
            entry_type=entry_type,
            symlink_target=symlink_target,
            filesystem_id=filesystem_id,
            observed_byte_size=observed_byte_size,
            observed_mtime_ns=observed_mtime_ns,
            availability=availability,
            last_seen_at=last_seen_at,
        )
        with self._write():
            if self._repository.get_asset(asset_id) is None:
                raise InvalidReferenceError("asset does not exist")
            root = self._repository.get_root(root_id)
            if root is None:
                raise InvalidReferenceError("library root does not exist")
            if (
                root.availability is RootAvailability.OFFLINE
                and availability is LocationAvailability.MISSING
            ):
                raise InvariantViolationError(
                    "an offline root cannot establish that a location is missing"
                )
            if (
                root.availability is RootAvailability.AVAILABLE
                and availability is LocationAvailability.OFFLINE
            ):
                raise InvariantViolationError("an offline location requires an offline root")
            try:
                self._repository.insert_location(location)
            except sqlite3.IntegrityError as error:
                raise UniquenessConflictError("active path already exists in this root") from error
        return self.get_location(location.id)

    def get_location(self, location_id: str) -> FileLocation:
        _uuid(location_id, "location_id")
        location = self._read(self._repository.get_location, location_id)
        if location is None:
            raise NotFoundError("file location does not exist")
        return location

    def list_root_locations(
        self, root_id: str, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
    ) -> list[FileLocation]:
        self.get_root(root_id)
        return self._read(self._repository.list_root_locations, root_id, *_page(limit, offset))

    def create_album(self, name: str, *, description: str | None = None) -> Album:
        name = _nonblank(name, "name")
        if description is not None and not isinstance(description, str):
            raise InvalidInputError("description must be a string or null")
        identifier = str(uuid.uuid4())
        with self._write():
            self._repository.insert_album(identifier, name, description)
        return self.get_album(identifier)

    def get_album(self, album_id: str) -> Album:
        _uuid(album_id, "album_id")
        album = self._read(self._repository.get_album, album_id)
        if album is None:
            raise NotFoundError("album does not exist")
        return album

    def list_albums(self, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> list[Album]:
        return self._read(self._repository.list_albums, *_page(limit, offset))

    def add_asset_to_album(self, album_id: str, asset_id: str) -> bool:
        _uuid(album_id, "album_id")
        _uuid(asset_id, "asset_id")
        with self._write():
            if self._repository.get_album(album_id) is None:
                raise InvalidReferenceError("album does not exist")
            if self._repository.get_asset(asset_id) is None:
                raise InvalidReferenceError("asset does not exist")
            return self._repository.add_album_asset(album_id, asset_id)

    def remove_asset_from_album(self, album_id: str, asset_id: str) -> bool:
        self.get_album(album_id)
        self.get_asset(asset_id)
        with self._write():
            return self._repository.remove_album_asset(album_id, asset_id)

    def list_album_assets(
        self, album_id: str, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
    ) -> list[Asset]:
        self.get_album(album_id)
        return self._read(self._repository.list_album_assets, album_id, *_page(limit, offset))

    def create_tag(self, display_name: str) -> Tag:
        if not isinstance(display_name, str):
            raise InvalidInputError("display_name must be a string")
        key = normalize_tag(display_name)
        if not key:
            raise InvalidInputError("tag name must not be empty after normalization")
        identifier = str(uuid.uuid4())
        with self._write():
            try:
                self._repository.insert_tag(identifier, display_name, key)
            except sqlite3.IntegrityError as error:
                raise UniquenessConflictError("normalized tag already exists") from error
        return self.get_tag(identifier)

    def get_tag(self, tag_id: str) -> Tag:
        _uuid(tag_id, "tag_id")
        tag = self._read(self._repository.get_tag, tag_id)
        if tag is None:
            raise NotFoundError("tag does not exist")
        return tag

    def list_tags(self, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> list[Tag]:
        return self._read(self._repository.list_tags, *_page(limit, offset))

    def add_tag_to_asset(self, asset_id: str, tag_id: str) -> None:
        _uuid(asset_id, "asset_id")
        _uuid(tag_id, "tag_id")
        with self._write():
            if self._repository.get_asset(asset_id) is None:
                raise InvalidReferenceError("asset does not exist")
            if self._repository.get_tag(tag_id) is None:
                raise InvalidReferenceError("tag does not exist")
            try:
                self._repository.add_asset_tag(asset_id, tag_id)
            except sqlite3.IntegrityError as error:
                raise DuplicateAssociationError("tag is already associated with asset") from error

    def remove_tag_from_asset(self, asset_id: str, tag_id: str) -> bool:
        self.get_asset(asset_id)
        self.get_tag(tag_id)
        with self._write():
            return self._repository.remove_asset_tag(asset_id, tag_id)

    def list_asset_tags(
        self, asset_id: str, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
    ) -> list[Tag]:
        self.get_asset(asset_id)
        return self._read(self._repository.list_asset_tags, asset_id, *_page(limit, offset))

    def get_annotation(self, asset_id: str) -> Annotation | None:
        self.get_asset(asset_id)
        return self._read(self._repository.get_annotation, asset_id)

    def set_rating(self, asset_id: str, rating: int | None) -> Annotation:
        if rating is not None and (
            isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5
        ):
            raise InvalidInputError("rating must be null or an integer from 1 to 5")
        return self._set_annotation(asset_id, "rating", rating)

    def set_favorite(self, asset_id: str, favorite: bool) -> Annotation:
        if not isinstance(favorite, bool):
            raise InvalidInputError("favorite must be boolean")
        return self._set_annotation(asset_id, "favorite", int(favorite))

    def set_title(self, asset_id: str, title: str | None) -> Annotation:
        if title is not None and not isinstance(title, str):
            raise InvalidInputError("title must be a string or null")
        return self._set_annotation(asset_id, "title", title)

    def set_description(self, asset_id: str, description: str | None) -> Annotation:
        if description is not None and not isinstance(description, str):
            raise InvalidInputError("description must be a string or null")
        return self._set_annotation(asset_id, "description", description)

    def _set_annotation(self, asset_id: str, field: str, value: object) -> Annotation:
        _uuid(asset_id, "asset_id")
        with self._write():
            if self._repository.get_asset(asset_id) is None:
                raise InvalidReferenceError("asset does not exist")
            self._repository.update_annotation(asset_id, field, value)
        annotation = self._read(self._repository.get_annotation, asset_id)
        if annotation is None:  # pragma: no cover - guarded by the transaction above
            raise PersistenceError("annotation update did not persist")
        return annotation

    @contextmanager
    def _write(self) -> Iterator[None]:
        if self._connection.in_transaction:
            raise InvariantViolationError("nested catalog transactions are not supported")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.DatabaseError as error:
            raise PersistenceError("could not start catalog transaction") from error
        try:
            yield
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._rollback_preserving(error)
            raise PersistenceError("unexpected catalog persistence failure") from error
        except sqlite3.DatabaseError as error:
            self._rollback_preserving(error)
            raise PersistenceError("unexpected catalog persistence failure") from error
        except Exception as error:
            self._rollback_preserving(error)
            raise

    def _rollback_preserving(self, original_error: BaseException) -> None:
        """Attempt rollback without replacing the operation's original failure."""
        try:
            self._connection.rollback()
        except sqlite3.DatabaseError:
            original_error.add_note("catalog rollback also failed")

    def _read(self, operation, *arguments):
        """Keep SQLite implementation errors outside the public catalog contract."""
        try:
            return operation(*arguments)
        except sqlite3.DatabaseError as error:
            raise PersistenceError("unexpected catalog persistence failure") from error


def _uuid(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise InvalidInputError(f"{name} must be a canonical UUID")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise InvalidInputError(f"{name} must be a canonical UUID") from error
    return value


def _enum(enum_type: type, value: object, name: str):
    try:
        return enum_type(value)
    except (ValueError, TypeError) as error:
        raise InvalidInputError(f"invalid {name}") from error


def _nonblank(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{name} must not be blank")
    return value


def _relative_path(value: str) -> str:
    value = _nonblank(value, "relative_path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise InvalidInputError("relative_path must be a canonical relative POSIX path")
    return value


def _page(limit: int, offset: int) -> tuple[int, int]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise InvalidInputError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise InvalidInputError("offset must be a non-negative integer")
    return limit, offset
