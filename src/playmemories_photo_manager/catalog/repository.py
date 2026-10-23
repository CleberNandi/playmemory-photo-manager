"""Concrete SQLite persistence for catalog use cases."""

from __future__ import annotations

import sqlite3

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


class CatalogRepository:
    """SQL operations on a caller-owned managed connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def insert_asset(
        self,
        identifier: str,
        kind: AssetKind,
        sha256: str | None,
        hash_state: HashState,
        byte_size: int | None,
        media_type: str | None,
    ) -> None:
        self.connection.execute(
            """INSERT INTO asset(id, kind, sha256, hash_state, byte_size, media_type)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (identifier, kind, sha256, hash_state, byte_size, media_type),
        )

    def get_asset(self, identifier: str) -> Asset | None:
        row = self.connection.execute(
            """SELECT id, kind, sha256, hash_state, byte_size, media_type, status, created_at
            FROM asset WHERE id = ?""",
            (identifier,),
        ).fetchone()
        return _asset(row) if row else None

    def list_assets(self, limit: int, offset: int) -> list[Asset]:
        rows = self.connection.execute(
            """SELECT id, kind, sha256, hash_state, byte_size, media_type, status, created_at
            FROM asset ORDER BY id LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        return [_asset(row) for row in rows]

    def insert_root(
        self,
        identifier: str,
        display_name: str,
        normalized_path: str,
        availability: RootAvailability,
    ) -> None:
        self.connection.execute(
            """INSERT INTO library_root(id, display_name, normalized_path, availability)
            VALUES (?, ?, ?, ?)""",
            (identifier, display_name, normalized_path, availability),
        )

    def get_root(self, identifier: str) -> LibraryRoot | None:
        row = self.connection.execute(
            """SELECT id, display_name, normalized_path, availability, created_at, last_checked_at
            FROM library_root WHERE id = ?""",
            (identifier,),
        ).fetchone()
        return _root(row) if row else None

    def list_roots(self, limit: int, offset: int) -> list[LibraryRoot]:
        rows = self.connection.execute(
            """SELECT id, display_name, normalized_path, availability, created_at, last_checked_at
            FROM library_root ORDER BY id LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        return [_root(row) for row in rows]

    def insert_location(self, location: FileLocation) -> None:
        self.connection.execute(
            """INSERT INTO file_location(
                id, asset_id, library_root_id, normalized_relative_path, entry_type,
                symlink_target, filesystem_id, observed_byte_size, observed_mtime_ns,
                availability, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                location.id,
                location.asset_id,
                location.library_root_id,
                location.normalized_relative_path,
                location.entry_type,
                location.symlink_target,
                location.filesystem_id,
                location.observed_byte_size,
                location.observed_mtime_ns,
                location.availability,
                location.last_seen_at,
            ),
        )

    def get_location(self, identifier: str) -> FileLocation | None:
        row = self.connection.execute(
            "SELECT * FROM file_location WHERE id = ?", (identifier,)
        ).fetchone()
        return _location(row) if row else None

    def list_asset_locations(self, asset_id: str, limit: int, offset: int) -> list[FileLocation]:
        rows = self.connection.execute(
            """SELECT * FROM file_location WHERE asset_id = ?
            ORDER BY id LIMIT ? OFFSET ?""",
            (asset_id, limit, offset),
        )
        return [_location(row) for row in rows]

    def list_root_locations(self, root_id: str, limit: int, offset: int) -> list[FileLocation]:
        rows = self.connection.execute(
            """SELECT * FROM file_location WHERE library_root_id = ?
            ORDER BY id LIMIT ? OFFSET ?""",
            (root_id, limit, offset),
        )
        return [_location(row) for row in rows]

    def insert_album(self, identifier: str, name: str, description: str | None) -> None:
        self.connection.execute(
            "INSERT INTO album(id, name, description) VALUES (?, ?, ?)",
            (identifier, name, description),
        )

    def get_album(self, identifier: str) -> Album | None:
        row = self.connection.execute(
            "SELECT id, name, description, created_at, updated_at FROM album WHERE id = ?",
            (identifier,),
        ).fetchone()
        return _album(row) if row else None

    def list_albums(self, limit: int, offset: int) -> list[Album]:
        rows = self.connection.execute(
            """SELECT id, name, description, created_at, updated_at FROM album
            ORDER BY id LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        return [_album(row) for row in rows]

    def add_album_asset(self, album_id: str, asset_id: str) -> bool:
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO album_asset(album_id, asset_id) VALUES (?, ?)",
            (album_id, asset_id),
        )
        return cursor.rowcount == 1

    def remove_album_asset(self, album_id: str, asset_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM album_asset WHERE album_id = ? AND asset_id = ?", (album_id, asset_id)
        )
        return cursor.rowcount == 1

    def list_album_assets(self, album_id: str, limit: int, offset: int) -> list[Asset]:
        rows = self.connection.execute(
            """SELECT a.id, a.kind, a.sha256, a.hash_state, a.byte_size, a.media_type,
                a.status, a.created_at
            FROM asset AS a JOIN album_asset AS aa ON aa.asset_id = a.id
            WHERE aa.album_id = ? ORDER BY a.id LIMIT ? OFFSET ?""",
            (album_id, limit, offset),
        )
        return [_asset(row) for row in rows]

    def insert_tag(self, identifier: str, display_name: str, normalized_key: str) -> None:
        self.connection.execute(
            "INSERT INTO tag(id, display_name, normalized_key) VALUES (?, ?, ?)",
            (identifier, display_name, normalized_key),
        )

    def get_tag(self, identifier: str) -> Tag | None:
        row = self.connection.execute(
            "SELECT id, display_name, normalized_key, created_at FROM tag WHERE id = ?",
            (identifier,),
        ).fetchone()
        return _tag(row) if row else None

    def list_tags(self, limit: int, offset: int) -> list[Tag]:
        rows = self.connection.execute(
            """SELECT id, display_name, normalized_key, created_at FROM tag
            ORDER BY id LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        return [_tag(row) for row in rows]

    def add_asset_tag(self, asset_id: str, tag_id: str) -> None:
        self.connection.execute(
            "INSERT INTO asset_tag(asset_id, tag_id) VALUES (?, ?)", (asset_id, tag_id)
        )

    def remove_asset_tag(self, asset_id: str, tag_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM asset_tag WHERE asset_id = ? AND tag_id = ?", (asset_id, tag_id)
        )
        return cursor.rowcount == 1

    def list_asset_tags(self, asset_id: str, limit: int, offset: int) -> list[Tag]:
        rows = self.connection.execute(
            """SELECT t.id, t.display_name, t.normalized_key, t.created_at
            FROM tag AS t JOIN asset_tag AS at ON at.tag_id = t.id
            WHERE at.asset_id = ? ORDER BY t.id LIMIT ? OFFSET ?""",
            (asset_id, limit, offset),
        )
        return [_tag(row) for row in rows]

    def get_annotation(self, asset_id: str) -> Annotation | None:
        row = self.connection.execute(
            """SELECT asset_id, rating, favorite, title, description, created_at, updated_at
            FROM user_annotation WHERE asset_id = ?""",
            (asset_id,),
        ).fetchone()
        return _annotation(row) if row else None

    def update_annotation(self, asset_id: str, field: str, value: object) -> None:
        if field not in {"rating", "favorite", "title", "description"}:
            raise ValueError("unsupported annotation field")
        self.connection.execute(
            f"""INSERT INTO user_annotation(asset_id, {field}) VALUES (?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET {field} = excluded.{field},
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            (asset_id, value),
        )


def _asset(row: sqlite3.Row) -> Asset:
    return Asset(
        id=row["id"],
        kind=AssetKind(row["kind"]),
        sha256=row["sha256"],
        hash_state=HashState(row["hash_state"]),
        byte_size=row["byte_size"],
        media_type=row["media_type"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _root(row: sqlite3.Row) -> LibraryRoot:
    return LibraryRoot(
        id=row["id"],
        display_name=row["display_name"],
        normalized_path=row["normalized_path"],
        availability=RootAvailability(row["availability"]),
        created_at=row["created_at"],
        last_checked_at=row["last_checked_at"],
    )


def _location(row: sqlite3.Row) -> FileLocation:
    return FileLocation(
        id=row["id"],
        asset_id=row["asset_id"],
        library_root_id=row["library_root_id"],
        normalized_relative_path=row["normalized_relative_path"],
        entry_type=EntryType(row["entry_type"]),
        symlink_target=row["symlink_target"],
        filesystem_id=row["filesystem_id"],
        observed_byte_size=row["observed_byte_size"],
        observed_mtime_ns=row["observed_mtime_ns"],
        availability=LocationAvailability(row["availability"]),
        last_seen_at=row["last_seen_at"],
    )


def _album(row: sqlite3.Row) -> Album:
    return Album(**dict(row))


def _tag(row: sqlite3.Row) -> Tag:
    return Tag(**dict(row))


def _annotation(row: sqlite3.Row) -> Annotation:
    values = dict(row)
    values["favorite"] = bool(values["favorite"])
    return Annotation(**values)
