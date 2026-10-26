"""POSIX-confined reader for pre-generated synthetic thumbnail fixtures."""

from __future__ import annotations

import os
import re
import stat
import uuid
from pathlib import Path

from .errors import (
    InvalidThumbnailError,
    ThumbnailNotFoundError,
    ThumbnailTooLargeError,
    UnsafeThumbnailPathError,
    UnsupportedThumbnailPlatformError,
)
from .models import (
    SyntheticThumbnailFixture,
    ThumbnailContent,
    ThumbnailReference,
    ThumbnailVariant,
)

_CACHE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


class SyntheticThumbnailStore:
    """Read only allowlisted files from one non-symlink POSIX cache directory."""

    def __init__(
        self,
        cache_root: str | Path,
        fixtures: tuple[SyntheticThumbnailFixture, ...],
        *,
        max_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise UnsupportedThumbnailPlatformError("secure synthetic cache requires POSIX")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise InvalidThumbnailError("max_bytes must be a positive integer")
        root = Path(cache_root)
        if not root.is_absolute():
            raise UnsafeThumbnailPathError("cache root must be absolute")
        _validate_ancestry(root)
        self._root = root
        self._max_bytes = max_bytes
        self._by_id: dict[str, SyntheticThumbnailFixture] = {}
        self._by_asset_variant: dict[tuple[str, ThumbnailVariant], SyntheticThumbnailFixture] = {}
        for fixture in fixtures:
            validated = _validate_fixture(fixture)
            key = (validated.asset_id, validated.variant)
            if validated.id in self._by_id or key in self._by_asset_variant:
                raise InvalidThumbnailError("duplicate synthetic thumbnail fixture")
            self._by_id[validated.id] = validated
            self._by_asset_variant[key] = validated

    def get_reference(self, asset_id: str, variant: ThumbnailVariant) -> ThumbnailReference | None:
        asset = _uuid(asset_id, "asset_id")
        try:
            normalized_variant = ThumbnailVariant(variant)
        except (ValueError, TypeError) as error:
            raise InvalidThumbnailError("unknown thumbnail variant") from error
        fixture = self._by_asset_variant.get((asset, normalized_variant))
        return _reference(fixture) if fixture else None

    def open(self, thumbnail_id: str) -> ThumbnailContent:
        identifier = _uuid(thumbnail_id, "thumbnail_id")
        fixture = self._by_id.get(identifier)
        if fixture is None:
            raise ThumbnailNotFoundError("thumbnail not found")
        root_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        file_flags = os.O_RDONLY | os.O_NOFOLLOW
        root_fd = -1
        file_fd = -1
        try:
            root_fd = os.open(self._root, root_flags)
            file_fd = os.open(fixture.cache_name, file_flags, dir_fd=root_fd)
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode):
                raise UnsafeThumbnailPathError("thumbnail cache entry is not a regular file")
            if before.st_size > self._max_bytes:
                raise ThumbnailTooLargeError("thumbnail exceeds the configured size limit")
            data = _read_limited(file_fd, self._max_bytes)
            after = os.fstat(file_fd)
            before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            if before_identity != after_identity:
                raise UnsafeThumbnailPathError("thumbnail changed while it was read")
            return ThumbnailContent(reference=_reference(fixture), data=data)
        except FileNotFoundError as error:
            raise ThumbnailNotFoundError("thumbnail not found") from error
        except OSError as error:
            raise UnsafeThumbnailPathError("thumbnail cache could not be opened safely") from error
        finally:
            if file_fd >= 0:
                os.close(file_fd)
            if root_fd >= 0:
                os.close(root_fd)


def _read_limited(file_fd: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        chunk = os.read(file_fd, min(remaining, 64 * 1024))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) > limit:
        raise ThumbnailTooLargeError("thumbnail exceeds the configured size limit")
    return data


def _validate_ancestry(root: Path) -> None:
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current /= part
        try:
            details = current.lstat()
        except OSError as error:
            raise UnsafeThumbnailPathError("cache root is unavailable") from error
        if stat.S_ISLNK(details.st_mode):
            raise UnsafeThumbnailPathError("cache root ancestry contains a symlink")
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise UnsafeThumbnailPathError("cache root is not a directory")


def _validate_fixture(fixture: SyntheticThumbnailFixture) -> SyntheticThumbnailFixture:
    identifier = _uuid(fixture.id, "thumbnail fixture id")
    asset_id = _uuid(fixture.asset_id, "thumbnail fixture asset id")
    try:
        variant = ThumbnailVariant(fixture.variant)
    except (ValueError, TypeError) as error:
        raise InvalidThumbnailError("unknown thumbnail variant") from error
    if not isinstance(fixture.cache_name, str) or not _CACHE_NAME.fullmatch(fixture.cache_name):
        raise InvalidThumbnailError("invalid thumbnail cache name")
    if fixture.media_type not in _MEDIA_TYPES:
        raise InvalidThumbnailError("unsupported thumbnail media type")
    return SyntheticThumbnailFixture(
        identifier, asset_id, variant, fixture.cache_name, fixture.media_type
    )


def _uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise InvalidThumbnailError(f"{field} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise InvalidThumbnailError(f"{field} must be a canonical UUID") from error
    if str(parsed) != value:
        raise InvalidThumbnailError(f"{field} must be a canonical UUID")
    return value


def _reference(fixture: SyntheticThumbnailFixture) -> ThumbnailReference:
    return ThumbnailReference(fixture.id, fixture.asset_id, fixture.variant, fixture.media_type)
