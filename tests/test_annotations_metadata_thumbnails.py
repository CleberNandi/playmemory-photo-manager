from __future__ import annotations

import sqlite3
import uuid

import pytest


def test_annotation_rating_favorite_and_text(database: sqlite3.Connection, asset_id: str) -> None:
    database.execute(
        "INSERT INTO user_annotation(asset_id, favorite, title, description) "
        "VALUES (?, 1, 'Title', 'Description')",
        (asset_id,),
    )
    assert tuple(
        database.execute(
            "SELECT rating, favorite, title, description FROM user_annotation"
        ).fetchone()
    ) == (None, 1, "Title", "Description")
    database.execute("UPDATE user_annotation SET rating = 1 WHERE asset_id = ?", (asset_id,))
    database.execute("UPDATE user_annotation SET rating = 5 WHERE asset_id = ?", (asset_id,))
    for invalid in (0, 6, 2.5):
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "UPDATE user_annotation SET rating = ? WHERE asset_id = ?", (invalid, asset_id)
            )


def test_only_one_annotation_per_asset(database: sqlite3.Connection, asset_id: str) -> None:
    database.execute("INSERT INTO user_annotation(asset_id) VALUES (?)", (asset_id,))
    with pytest.raises(sqlite3.IntegrityError):
        database.execute("INSERT INTO user_annotation(asset_id) VALUES (?)", (asset_id,))


def _metadata(database: sqlite3.Connection, asset_id: str, **overrides: object) -> str:
    identifier = str(uuid.uuid4())
    values = {
        "id": identifier,
        "asset_id": asset_id,
        "namespace": "exif",
        "metadata_key": "DateTimeOriginal",
        "source": "embedded-exif",
        "source_key": "Exif.Photo.DateTimeOriginal",
        "raw_value": "2026:10:23 14:30:00",
        "interpreted_value": "2026-10-23T14:30:00",
        "value_type": "datetime",
        "temporal_local_value": "2026-10-23T14:30:00",
        "temporal_precision": "second",
        "timezone_state": "unknown",
        "utc_offset_minutes": None,
        "timezone_name": None,
        "extractor_version": "test/1",
        "extracted_at": "2026-10-23T18:00:00Z",
        "conflict_group": None,
        "is_conflicting": 0,
    }
    values.update(overrides)
    database.execute(
        """INSERT INTO metadata(
            id, asset_id, namespace, metadata_key, source, source_key, raw_value,
            interpreted_value, value_type, temporal_local_value, temporal_precision,
            timezone_state, utc_offset_minutes, timezone_name, extractor_version, extracted_at,
            conflict_group, is_conflicting
        ) VALUES (
            :id, :asset_id, :namespace, :metadata_key, :source, :source_key, :raw_value,
            :interpreted_value, :value_type, :temporal_local_value, :temporal_precision,
            :timezone_state, :utc_offset_minutes, :timezone_name, :extractor_version, :extracted_at,
            :conflict_group, :is_conflicting
        )""",
        values,
    )
    return identifier


def test_floating_time_preserves_raw_value_without_utc(
    database: sqlite3.Connection, asset_id: str
) -> None:
    metadata_id = _metadata(database, asset_id)
    row = database.execute(
        "SELECT raw_value, temporal_local_value, timezone_state, utc_offset_minutes "
        "FROM metadata WHERE id = ?",
        (metadata_id,),
    ).fetchone()
    assert tuple(row) == ("2026:10:23 14:30:00", "2026-10-23T14:30:00", "unknown", None)


def test_explicit_offset_and_precision_are_preserved(
    database: sqlite3.Connection, asset_id: str
) -> None:
    metadata_id = _metadata(
        database,
        asset_id,
        raw_value="2026-10-23T14:30:00-03:00",
        timezone_state="offset",
        utc_offset_minutes=-180,
        temporal_precision="minute",
    )
    row = database.execute(
        "SELECT timezone_state, utc_offset_minutes, temporal_precision FROM metadata WHERE id = ?",
        (metadata_id,),
    ).fetchone()
    assert tuple(row) == ("offset", -180, "minute")


def test_invalid_timezone_representation_is_rejected(
    database: sqlite3.Connection, asset_id: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _metadata(database, asset_id, timezone_state="unknown", utc_offset_minutes=-180)


def test_timezone_requires_a_temporal_value_and_consistent_state(
    database: sqlite3.Connection, asset_id: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _metadata(
            database,
            asset_id,
            temporal_local_value=None,
            temporal_precision=None,
            timezone_state=None,
            timezone_name="Europe/Paris",
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "UPDATE asset SET captured_timezone_state = 'unknown' WHERE id = ?", (asset_id,)
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO user_annotation(asset_id, corrected_timezone_name) VALUES (?, 'UTC')",
            (asset_id,),
        )


def test_conflicting_sources_coexist(database: sqlite3.Connection, asset_id: str) -> None:
    _metadata(database, asset_id, conflict_group="capture-1", is_conflicting=1)
    _metadata(
        database,
        asset_id,
        namespace="xmp",
        source="sidecar-xmp",
        source_key="xmp:CreateDate",
        raw_value="2026-10-24",
        interpreted_value="2026-10-24",
        temporal_local_value="2026-10-24",
        temporal_precision="day",
        conflict_group="capture-1",
        is_conflicting=1,
    )
    assert database.execute("SELECT count(DISTINCT source) FROM metadata").fetchone()[0] == 2


def test_manual_correction_does_not_overwrite_extracted_metadata(
    database: sqlite3.Connection, asset_id: str
) -> None:
    metadata_id = _metadata(database, asset_id)
    database.execute(
        """INSERT INTO user_annotation(
            asset_id, corrected_local_value, corrected_precision,
            corrected_timezone_state, correction_reason
        ) VALUES (?, '2026-10-25', 'day', 'unknown', 'camera clock was wrong')""",
        (asset_id,),
    )
    database.execute(
        """UPDATE asset SET captured_local_value = '2026-10-25', captured_precision = 'day',
            captured_timezone_state = 'unknown', captured_source_kind = 'manual',
            captured_selection_reason = 'active manual correction' WHERE id = ?""",
        (asset_id,),
    )
    assert (
        database.execute("SELECT raw_value FROM metadata WHERE id = ?", (metadata_id,)).fetchone()[
            0
        ]
        == "2026:10:23 14:30:00"
    )
    assert (
        database.execute(
            "SELECT captured_source_kind FROM asset WHERE id = ?", (asset_id,)
        ).fetchone()[0]
        == "manual"
    )


def test_selected_metadata_is_restrictively_referenced(
    database: sqlite3.Connection, asset_id: str
) -> None:
    metadata_id = _metadata(database, asset_id)
    database.execute(
        """UPDATE asset SET captured_local_value = '2026-10-23T14:30:00',
            captured_precision = 'second',
            captured_timezone_state = 'unknown', captured_source_kind = 'metadata',
            captured_metadata_id = ?, captured_selection_reason = 'EXIF precedence' WHERE id = ?""",
        (metadata_id, asset_id),
    )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute("DELETE FROM metadata WHERE id = ?", (metadata_id,))


def test_selected_metadata_must_belong_to_same_asset(
    database: sqlite3.Connection, asset_id: str
) -> None:
    other_asset = str(uuid.uuid4())
    database.execute("INSERT INTO asset(id, kind) VALUES (?, 'photo')", (other_asset,))
    metadata_id = _metadata(database, other_asset)
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            """UPDATE asset SET captured_local_value = '2026-10-23', captured_precision = 'day',
                captured_timezone_state = 'unknown', captured_source_kind = 'metadata',
                captured_metadata_id = ? WHERE id = ?""",
            (metadata_id, asset_id),
        )


def test_thumbnail_has_no_blob_and_cascades_with_asset(
    database: sqlite3.Connection, asset_id: str
) -> None:
    database.execute(
        """INSERT INTO thumbnail(
            id, asset_id, variant, cache_relative_path, generator_version,
            source_fingerprint, width, height
        ) VALUES (?, ?, 'grid', 'ab/thumb.webp', '1', 'sha256:abc', 256, 256)""",
        (str(uuid.uuid4()), asset_id),
    )
    columns = {row[1] for row in database.execute("PRAGMA table_info(thumbnail)")}
    assert "content" not in columns and "blob" not in columns
    database.execute("DELETE FROM asset WHERE id = ?", (asset_id,))
    assert database.execute("SELECT count(*) FROM thumbnail").fetchone()[0] == 0
