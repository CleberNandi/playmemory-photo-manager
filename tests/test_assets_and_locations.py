from __future__ import annotations

import sqlite3
import uuid

import pytest


def _asset(database: sqlite3.Connection, identifier: str, sha256: str | None = None) -> None:
    database.execute(
        "INSERT INTO asset(id, kind, sha256, hash_state) VALUES (?, 'photo', ?, ?)",
        (identifier, sha256, "verified" if sha256 else "absent"),
    )


def test_asset_identity_is_independent_of_path_and_hash(
    database: sqlite3.Connection, root_id: str
) -> None:
    digest = "a" * 64
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    _asset(database, first, digest)
    _asset(database, second, digest)
    database.execute(
        "INSERT INTO file_location(id, asset_id, library_root_id, normalized_relative_path) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), first, root_id, "2026/one.jpg"),
    )
    database.execute(
        "INSERT INTO file_location(id, asset_id, library_root_id, normalized_relative_path) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), second, root_id, "2026/two.jpg"),
    )
    assert (
        database.execute("SELECT count(*) FROM asset WHERE sha256 = ?", (digest,)).fetchone()[0]
        == 2
    )


def test_asset_requires_canonical_uuid_and_id_is_immutable(database: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        database.execute("INSERT INTO asset(id, kind) VALUES ('not-a-uuid', 'photo')")
    identifier = str(uuid.uuid4())
    database.execute("INSERT INTO asset(id, kind) VALUES (?, 'photo')", (identifier,))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        database.execute("UPDATE asset SET id = ? WHERE id = ?", (str(uuid.uuid4()), identifier))


def test_asset_can_have_multiple_locations_and_hardlinks(
    database: sqlite3.Connection, asset_id: str, root_id: str
) -> None:
    for path in ("a/photo.jpg", "b/photo-hardlink.jpg"):
        database.execute(
            "INSERT INTO file_location("
            "id, asset_id, library_root_id, normalized_relative_path, filesystem_id"
            ") VALUES (?, ?, ?, ?, 'dev1:inode9')",
            (str(uuid.uuid4()), asset_id, root_id, path),
        )
    rows = database.execute("SELECT DISTINCT asset_id, filesystem_id FROM file_location").fetchall()
    assert [tuple(row) for row in rows] == [(asset_id, "dev1:inode9")]
    assert database.execute("SELECT count(*) FROM file_location").fetchone()[0] == 2


def test_active_path_is_unique_within_root(
    database: sqlite3.Connection, asset_id: str, root_id: str
) -> None:
    values = (str(uuid.uuid4()), asset_id, root_id, "same/photo.jpg")
    database.execute(
        "INSERT INTO file_location(id, asset_id, library_root_id, normalized_relative_path) "
        "VALUES (?, ?, ?, ?)",
        values,
    )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO file_location("
            "id, asset_id, library_root_id, normalized_relative_path, availability"
            ") VALUES (?, ?, ?, ?, 'offline')",
            (str(uuid.uuid4()), asset_id, root_id, "same/photo.jpg"),
        )


def test_same_relative_path_is_allowed_in_different_roots(
    database: sqlite3.Connection, asset_id: str, root_id: str
) -> None:
    other_root = str(uuid.uuid4())
    database.execute(
        "INSERT INTO library_root(id, display_name, normalized_path) "
        "VALUES (?, 'Backup', '/backup')",
        (other_root,),
    )
    for root in (root_id, other_root):
        database.execute(
            "INSERT INTO file_location(id, asset_id, library_root_id, normalized_relative_path) "
            "VALUES (?, ?, ?, 'photo.jpg')",
            (str(uuid.uuid4()), asset_id, root),
        )
    assert database.execute("SELECT count(*) FROM file_location").fetchone()[0] == 2


def test_offline_root_is_distinct_from_missing_file(
    database: sqlite3.Connection, asset_id: str, root_id: str
) -> None:
    database.execute("UPDATE library_root SET availability = 'offline' WHERE id = ?", (root_id,))
    database.execute(
        "INSERT INTO file_location("
        "id, asset_id, library_root_id, normalized_relative_path, availability"
        ") VALUES (?, ?, ?, 'unknown.jpg', 'offline')",
        (str(uuid.uuid4()), asset_id, root_id),
    )
    root_state, location_state = database.execute(
        "SELECT r.availability, f.availability FROM library_root r "
        "JOIN file_location f ON f.library_root_id = r.id"
    ).fetchone()
    assert (root_state, location_state) == ("offline", "offline")
    database.execute("UPDATE library_root SET availability = 'available' WHERE id = ?", (root_id,))
    database.execute("UPDATE file_location SET availability = 'missing'")
    assert database.execute("SELECT availability FROM file_location").fetchone()[0] == "missing"


def test_asset_with_location_cannot_be_deleted_accidentally(
    database: sqlite3.Connection, asset_id: str, root_id: str
) -> None:
    database.execute(
        "INSERT INTO file_location(id, asset_id, library_root_id, normalized_relative_path) "
        "VALUES (?, ?, ?, 'kept.jpg')",
        (str(uuid.uuid4()), asset_id, root_id),
    )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute("DELETE FROM asset WHERE id = ?", (asset_id,))
