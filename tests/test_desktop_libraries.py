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
