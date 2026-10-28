from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

import pytest

from playmemories_photo_manager.catalog import initialize_database
from playmemories_photo_manager.desktop.bridge import _open_catalog, serve

TOKEN = "a" * 32


def _run(*requests: object) -> tuple[int, list[dict]]:
    connection = initialize_database(":memory:")
    source = io.StringIO("".join(json.dumps(request) + "\n" for request in requests))
    sink = io.StringIO()
    try:
        status = serve(connection, TOKEN, source, sink)
    finally:
        connection.close()
    return status, [json.loads(line) for line in sink.getvalue().splitlines()]


def test_gallery_list_uses_read_only_gallery_contract() -> None:
    status, messages = _run(
        {"id": "one", "token": TOKEN, "method": "gallery.list", "params": {"page_size": 12}}
    )

    assert status == 0
    assert messages == [
        {"event": "ready", "protocol": 1},
        {
            "id": "one",
            "ok": True,
            "result": {"items": [], "next_cursor": None, "has_more": False},
        },
    ]


def test_bridge_rejects_wrong_token_and_unknown_method_without_leaking_details() -> None:
    _, messages = _run(
        {"id": "bad-token", "token": "wrong", "method": "gallery.list"},
        {"id": "bad-method", "token": TOKEN, "method": "filesystem.read", "params": {}},
    )

    assert [message["error"]["code"] for message in messages[1:]] == [
        "invalid_request",
        "invalid_request",
    ]


def test_shutdown_is_explicit_and_stops_processing() -> None:
    status, messages = _run(
        {"id": "stop", "token": TOKEN, "method": "shutdown"},
        {"id": "ignored", "token": TOKEN, "method": "gallery.list"},
    )

    assert status == 0
    assert messages[-1] == {"id": "stop", "ok": True, "result": {"accepted": True}}
    assert all(message.get("id") != "ignored" for message in messages)


@pytest.mark.parametrize("filename", ["catálogo #1.sqlite", "catalog?draft.sqlite"])
def test_catalog_uri_escapes_reserved_and_unicode_characters(tmp_path: Path, filename: str) -> None:
    catalog = tmp_path / filename
    writable = initialize_database(catalog)
    writable.close()
    before = {path.name for path in tmp_path.iterdir()}

    connection = _open_catalog(catalog)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE forbidden (id INTEGER)")
    finally:
        connection.close()

    assert {path.name for path in tmp_path.iterdir()} == before
