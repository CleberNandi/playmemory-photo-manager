from __future__ import annotations

import sqlite3
import uuid

import pytest

from playmemories_photo_manager.catalog import create_tag, normalize_tag


def test_album_many_to_many_and_duplicate_rejected(
    database: sqlite3.Connection, asset_id: str
) -> None:
    other_asset, first_album, second_album = (str(uuid.uuid4()) for _ in range(3))
    database.execute("INSERT INTO asset(id, kind) VALUES (?, 'photo')", (other_asset,))
    database.execute("INSERT INTO album(id, name) VALUES (?, 'First')", (first_album,))
    database.execute("INSERT INTO album(id, name) VALUES (?, 'Second')", (second_album,))
    database.execute(
        "INSERT INTO album_asset(album_id, asset_id) VALUES (?, ?)", (first_album, asset_id)
    )
    database.execute(
        "INSERT INTO album_asset(album_id, asset_id) VALUES (?, ?)", (first_album, other_asset)
    )
    database.execute(
        "INSERT INTO album_asset(album_id, asset_id) VALUES (?, ?)", (second_album, asset_id)
    )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO album_asset(album_id, asset_id) VALUES (?, ?)", (first_album, asset_id)
        )


def test_deleting_album_only_removes_membership(
    database: sqlite3.Connection, asset_id: str
) -> None:
    album_id = str(uuid.uuid4())
    database.execute("INSERT INTO album(id, name) VALUES (?, 'Temporary')", (album_id,))
    database.execute(
        "INSERT INTO album_asset(album_id, asset_id) VALUES (?, ?)", (album_id, asset_id)
    )
    database.execute("DELETE FROM album WHERE id = ?", (album_id,))
    assert (
        database.execute("SELECT count(*) FROM asset WHERE id = ?", (asset_id,)).fetchone()[0] == 1
    )
    assert database.execute("SELECT count(*) FROM album_asset").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" Viagem ", "viagem"),
        ("CAFÉ", "café"),
        ("cafe", "cafe"),
        ("Ｆｏｔｏ", "foto"),
        ("duas\t  palavras", "duas palavras"),
        ("Straße", "strasse"),
    ],
)
def test_tag_normalization(value: str, expected: str) -> None:
    assert normalize_tag(value) == expected


def test_tag_key_is_unique_and_accents_are_preserved(database: sqlite3.Connection) -> None:
    first = create_tag(database, "Viagem")
    with pytest.raises(sqlite3.IntegrityError):
        create_tag(database, " viagem ")
    cafe = create_tag(database, "cafe")
    cafe_accent = create_tag(database, "CAFÉ")
    assert len({first, cafe, cafe_accent}) == 3
    assert [
        tuple(row)
        for row in database.execute("SELECT normalized_key FROM tag ORDER BY normalized_key")
    ] == [("cafe",), ("café",), ("viagem",)]


def test_database_rejects_inconsistent_tag_key(database: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO tag(id, display_name, normalized_key) VALUES (?, 'Viagem', 'wrong')",
            (str(uuid.uuid4()),),
        )


def test_empty_normalized_tag_is_rejected_by_application(database: sqlite3.Connection) -> None:
    with pytest.raises(ValueError):
        create_tag(database, " \t ")


def test_tag_many_to_many_and_duplicate_rejected(
    database: sqlite3.Connection, asset_id: str
) -> None:
    tag_id = create_tag(database, "Família")
    database.execute("INSERT INTO asset_tag(asset_id, tag_id) VALUES (?, ?)", (asset_id, tag_id))
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO asset_tag(asset_id, tag_id) VALUES (?, ?)", (asset_id, tag_id)
        )
