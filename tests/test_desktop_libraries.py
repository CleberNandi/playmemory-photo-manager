import io
import json
from uuid import uuid4

import pytest

from playmemories_photo_manager.desktop.bridge import serve
from playmemories_photo_manager.desktop.libraries import LibraryDispatcher
from playmemories_photo_manager.library import LibraryError


def test_session_bound_create_switch_close_and_failure(tmp_path):
    dispatcher = LibraryDispatcher()
    try:
        assert dispatcher.request("library.state", {}) == {"state": "no_library", "session": None}
        first = dispatcher.request(
            "library.create", {"path": str(tmp_path / "first"), "library_handle": str(uuid4())}
        )
        identifier = first["session"]["session_id"]
        assert "path" not in first["session"]
        with pytest.raises(LibraryError, match="not_found"):
            dispatcher.request(
                "library.open", {"path": str(tmp_path / "missing"), "library_handle": str(uuid4())}
            )
        assert dispatcher.state() == first
        assert not dispatcher.request("gallery.list", {"session_id": identifier})["items"]
        second = dispatcher.request(
            "library.create", {"path": str(tmp_path / "second"), "library_handle": str(uuid4())}
        )
        assert second["session"]["session_id"] != identifier
        with pytest.raises(LibraryError, match="stale_session"):
            dispatcher.request("gallery.list", {"session_id": identifier})
        dispatcher.request("library.close", {"session_id": second["session"]["session_id"]})
        assert dispatcher.state()["state"] == "no_library"
    finally:
        dispatcher.close()


@pytest.mark.parametrize(
    "method,params",
    [
        ("library.create", {"path": "relative", "library_handle": "bad"}),
        ("library.open", {"path": "/unvisited", "library_handle": str(uuid4()), "extra": True}),
        ("library.state", {"path": "/unvisited"}),
        ("library.close", {"session_id": "bad"}),
        ("gallery.list", {}),
        ("filesystem.read", {}),
    ],
)
def test_invalid_inputs_never_observe_media(method, params):
    dispatcher = LibraryDispatcher()
    try:
        with pytest.raises(LibraryError):
            dispatcher.request(method, params)
    finally:
        dispatcher.close()


def test_transport_rejects_duplicate_deep_extra_and_oversized_requests():
    token = "a" * 32
    lines = [
        '{"id":"x","id":"y","token":"' + token + '","method":"library.state"}\n',
        json.dumps({"id": "x", "token": token, "method": "library.state", "extra": 1}) + "\n",
        json.dumps(
            {
                "id": "x",
                "token": token,
                "method": "library.state",
                "params": [[[[[[[[[[[[[[1]]]]]]]]]]]]]],
            }
        )
        + "\n",
        "x" * 70000 + "\n",
        json.dumps({"id": "valid", "token": token, "method": "library.state", "params": {}}) + "\n",
    ]
    dispatcher = LibraryDispatcher()
    output = io.StringIO()
    try:
        serve(None, token, io.StringIO("".join(lines)), output, libraries=dispatcher)
    finally:
        dispatcher.close()
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [m["error"]["code"] for m in messages[1:-1]] == [
        "invalid_request",
        "invalid_request",
        "invalid_request",
        "message_too_large",
    ]
    assert messages[-1]["result"]["state"] == "no_library"


def test_transport_lifecycle_sanitizes_private_error(tmp_path):
    dispatcher = LibraryDispatcher()
    output = io.StringIO()
    request = {
        "id": "one",
        "token": "a" * 32,
        "method": "library.open",
        "params": {"path": str(tmp_path / "private-name"), "library_handle": str(uuid4())},
    }
    try:
        serve(None, "a" * 32, io.StringIO(json.dumps(request) + "\n"), output, libraries=dispatcher)
    finally:
        dispatcher.close()
    assert "private-name" not in output.getvalue()
    assert json.loads(output.getvalue().splitlines()[-1])["error"] == {"code": "not_found"}


def test_root_remove_clears_catalog_entries_without_touching_disk(tmp_path):
    from playmemories_photo_manager.catalog import Catalog
    from playmemories_photo_manager.catalog.database import connect

    media = tmp_path / "media"
    media.mkdir()
    photo = media / "photo.jpg"
    photo.write_bytes(b"synthetic-photo")
    catalog_path = tmp_path / "catalog.sqlite3"
    dispatcher = LibraryDispatcher()
    try:
        state = dispatcher.request(
            "library.create",
            {"path": str(catalog_path), "library_handle": str(uuid4())},
        )
        session_id = state["session"]["session_id"]
        with connect(catalog_path) as connection:
            catalog = Catalog(connection)
            root = catalog.register_root("Teste", str(media))
            asset = catalog.create_asset("photo")
            meta_id = str(uuid4())
            connection.execute(
                """INSERT INTO metadata(id, asset_id, namespace, metadata_key, source, source_key,
                raw_value, extractor_version, extracted_at)
                VALUES (?, ?, 'exif', 'captured_at', 'exif', 'DateTimeOriginal',
                '2026:11:16 10:00:00', '1', '2026-11-16T10:00:00Z')""",
                (meta_id, asset.id),
            )
            connection.execute(
                """UPDATE asset SET captured_metadata_id=?, captured_source_kind='metadata',
                captured_local_value='2026-11-16T10:00:00', captured_precision='second',
                captured_timezone_state='unknown' WHERE id=?""",
                (meta_id, asset.id),
            )
            catalog.register_location(
                asset.id, root.id, "photo.jpg", last_seen_at="2026-11-16T00:00:00Z"
            )
        removed = dispatcher.request("root.remove", {"session_id": session_id, "root_id": root.id})
        assert removed == {
            "status": "removed",
            "root_id": root.id,
        }
        assert photo.read_bytes() == b"synthetic-photo"
        gallery = dispatcher.request(
            "gallery.list",
            {"session_id": session_id, "include_roots": True, "exclude_missing": True},
        )
        assert gallery["roots"] == []
        assert list(gallery["items"]) == []
        with pytest.raises(LibraryError, match="not_found"):
            dispatcher.request("root.remove", {"session_id": session_id, "root_id": root.id})
    finally:
        dispatcher.close()
