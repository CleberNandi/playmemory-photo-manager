"""Read-only details transport, using only synthetic catalogs."""

import io
import json
import sqlite3
from dataclasses import asdict

import pytest

from playmemories_photo_manager.desktop.bridge import _dispatch, serve
from playmemories_photo_manager.desktop.demo import open_demo_catalog
from playmemories_photo_manager.gallery import GalleryQueries


def request(connection, asset_id):
    source = io.StringIO(
        json.dumps(
            {
                "id": "details",
                "token": "test",
                "method": "asset.details",
                "params": {"asset_id": asset_id},
            }
        )
        + "\n"
    )
    sink = io.StringIO()
    serve(connection, "test", source, sink)
    return json.loads(sink.getvalue().splitlines()[-1])


def test_details_serializes_existing_projection_without_paths_or_writes():
    connection = open_demo_catalog()
    try:
        asset_id = GalleryQueries(connection).list_assets().items[0].asset_id
        before = connection.total_changes
        result = request(connection, asset_id)
        assert result["ok"]
        assert result["result"] == json.loads(
            json.dumps(asdict(GalleryQueries(connection).get_asset_details(asset_id)))
        )
        assert result["result"]["metadata_state"] == "not_extracted"
        assert result["result"]["capture"] is None
        assert "/synthetic-demo" not in json.dumps(result)
        assert connection.total_changes == before
    finally:
        connection.close()


@pytest.mark.parametrize(
    "identifier", ["../private", "A" * 32, None, 1, "00000000000000000000000000000000"]
)
def test_invalid_uuid_is_rejected(identifier):
    connection = open_demo_catalog()
    try:
        assert request(connection, identifier)["error"]["code"] == "invalid_request"
    finally:
        connection.close()


def test_nonexistent_asset_and_strict_params():
    connection = open_demo_catalog()
    try:
        assert request(connection, "00000000-0000-0000-0000-000000000000")["error"] == {
            "code": "not_found"
        }
        with pytest.raises(ValueError):
            _dispatch(
                connection,
                "asset.details",
                {"asset_id": "00000000-0000-0000-0000-000000000000", "path": "/private"},
            )
    finally:
        connection.close()


@pytest.mark.parametrize(
    "failure,code",
    [
        (RuntimeError("/private/token"), "backend_failure"),
        (sqlite3.OperationalError("/private"), "backend_failure"),
    ],
)
def test_internal_errors_are_sanitized(monkeypatch, failure, code):
    connection = open_demo_catalog()

    def fail(*args):
        raise failure

    monkeypatch.setattr(GalleryQueries, "get_asset_details", fail)
    try:
        result = request(connection, "00000000-0000-0000-0000-000000000000")
        assert result["error"]["code"] == code
        assert "private" not in json.dumps(result)
    finally:
        connection.close()


def test_busy_is_temporary(monkeypatch):
    error = sqlite3.OperationalError("private database locked")
    error.sqlite_errorcode = sqlite3.SQLITE_BUSY
    connection = open_demo_catalog()

    def fail(*args):
        raise error

    monkeypatch.setattr(GalleryQueries, "get_asset_details", fail)
    try:
        assert request(connection, "00000000-0000-0000-0000-000000000000")["error"] == {
            "code": "temporarily_unavailable"
        }
    finally:
        connection.close()


def test_transport_preserves_locations_limit_and_metadata_provenance():
    from uuid import UUID

    connection = open_demo_catalog()
    try:
        connection.execute("PRAGMA query_only = OFF")
        asset_id, root_id = connection.execute(
            "SELECT asset_id, library_root_id FROM file_location LIMIT 1"
        ).fetchone()
        for index in range(101):
            connection.execute(
                """INSERT INTO file_location(id, asset_id, library_root_id,
                normalized_relative_path, availability, entry_type)
                VALUES (?, ?, ?, ?, 'missing', 'file')""",
                (str(UUID(int=index + 1)), asset_id, root_id, f"lab-{index}.jpg"),
            )
        connection.execute(
            """INSERT INTO metadata(id, asset_id, namespace, metadata_key, source,
            source_key, raw_value, extractor_version, extracted_at, conflict_group,
            is_conflicting) VALUES (?, ?, 'catalog', 'lab-example', 'synthetic-lab',
            'fixture', 'synthetic raw value', 'synthetic-v1',
            '2026-01-01T00:00:00Z', 'synthetic-conflict', 1)""",
            (str(UUID(int=1000)), asset_id),
        )
        connection.execute(
            "UPDATE file_location SET observed_mtime_ns = 1700000000000000001 WHERE asset_id = ?",
            (asset_id,),
        )
        connection.execute("PRAGMA query_only = ON")
        result = request(connection, asset_id)["result"]
        assert result["locations"][0]["observed_mtime_ns"] == "1700000000000000001"
        assert len(result["locations"]) == 100
        assert result["locations_truncated"] is True
        assert result["metadata_state"] == "extracted"
        assert result["metadata"][0]["source"] == "synthetic-lab"
        assert result["metadata"][0]["is_conflicting"] is True
        assert result["metadata"][0]["interpreted_value"] is None
    finally:
        connection.close()
