"""Actual authenticated pipe bridge; synthetic media only, idle pumping and cleanup."""

import json
import os
import select
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from jpeg_fixtures import jpeg

TOKEN = "s" * 64


class Client:
    def __init__(self, enabled=True):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "playmemories_photo_manager.desktop.bridge"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "PLAYMEMORIES_BRIDGE_TOKEN": TOKEN,
                "PLAYMEMORIES_DESKTOP_INGESTION_LAB": "1" if enabled else "0",
                "PLAYMEMORIES_DESKTOP_PROTECTED_PATHS": "[]",
            },
        )
        self.pending = bytearray()
        assert self.read()["event"] == "ready"

    def read(self, timeout=8):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.pending:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "bridge response timed out"
            assert select.select([self.process.stdout], [], [], remaining)[0]
            chunk = os.read(self.process.stdout.fileno(), 65536)
            assert chunk, self.process.stderr.read().decode()
            self.pending.extend(chunk)
        end = self.pending.index(10) + 1
        line = self.pending[:end]
        del self.pending[:end]
        return json.loads(line)

    def send(self, method, params=None, **envelope):
        message = {
            "id": str(uuid4()),
            "token": TOKEN,
            "method": method,
            "params": params or {},
        } | envelope
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()
        return message["id"]

    def request(self, method, params=None):
        identifier = self.send(method, params)
        result = self.read()
        assert result["id"] == identifier
        return result

    def close(self):
        if self.process.poll() is None:
            try:
                self.request("shutdown")
                self.process.wait(timeout=5)
            finally:
                if self.process.poll() is None:
                    self.process.kill()
                    self.process.wait(timeout=3)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


@pytest.fixture
def client():
    instance = Client()
    yield instance
    instance.close()


def setup(client, tmp_path, count=1):
    root = tmp_path / "media"
    root.mkdir()
    for i in range(count):
        (root / f"{i}.jpg").write_bytes(jpeg())
    state = client.request(
        "library.create",
        {"path": str(tmp_path / "catalog.sqlite3"), "library_handle": str(uuid4())},
    )
    context = {"session_id": state["result"]["session"]["session_id"], "window_id": str(uuid4())}
    grant = client.request(
        "ingestion.select_root",
        context | {"path": str(root), "recursive": True, "identity_reviewed": True},
    )
    assert grant["ok"], grant
    job = client.request(
        "ingestion.prepare",
        context
        | {
            "root_grant_id": grant["result"]["root_grant_id"],
            "recursive": True,
            "client_request_id": str(uuid4()),
        },
    )
    assert job["ok"], job
    return root, context, job["result"]["operation_id"]


def test_idle_worker_completes_and_pages_without_exposing_paths(client, tmp_path):
    root, scope, operation = setup(client, tmp_path, 3)
    # No input arrives while the host must drain and reap the worker.
    time.sleep(1.5)
    status = client.request("ingestion.status", scope | {"operation_id": operation})
    assert status["result"]["state"] == "completed", status
    proposal = status["result"]["proposal_id"]
    page = client.request(
        "ingestion.page", scope | {"proposal_id": proposal, "cursor": None, "page_size": 2}
    )
    assert len(page["result"]["items"]) == 2
    assert str(root) not in json.dumps(page)
    crossed = client.request(
        "ingestion.status", scope | {"operation_id": operation, "window_id": str(uuid4())}
    )
    assert crossed["error"]["code"] == "stale_session"


def test_partial_input_does_not_block_tick(client, tmp_path):
    _root, scope, operation = setup(client, tmp_path)
    identifier = str(uuid4())
    line = json.dumps(
        {
            "id": identifier,
            "token": TOKEN,
            "method": "ingestion.status",
            "params": scope | {"operation_id": operation},
        }
    ).encode()
    client.process.stdin.write(line[:20])
    client.process.stdin.flush()
    time.sleep(1.5)
    client.process.stdin.write(line[20:] + b"\n")
    client.process.stdin.flush()
    assert client.read()["result"]["state"] == "completed"


def test_shutdown_ack_requires_worker_cleanup(client, tmp_path):
    setup(client, tmp_path, 100)
    result = client.request("shutdown")
    assert result["result"] == {"accepted": True}
    assert client.process.wait(timeout=3) == 0


def test_disabled_routes_never_select(tmp_path):
    client = Client(enabled=False)
    try:
        state = client.request(
            "library.create", {"path": str(tmp_path / "catalog"), "library_handle": str(uuid4())}
        )
        result = client.request(
            "ingestion.select_root",
            {
                "session_id": state["result"]["session"]["session_id"],
                "window_id": str(uuid4()),
                "path": str(tmp_path),
                "recursive": True,
                "identity_reviewed": True,
            },
        )
        assert result["error"]["code"] == "unavailable"
    finally:
        client.close()


def test_bad_auth_and_utf8_recover_without_observing_selection(client):
    client.send("ingestion.select_root", {"path": "/unvisited"}, token="wrong")
    assert client.read()["error"]["code"] == "invalid_request"
    client.process.stdin.write(b"\xff\n")
    client.process.stdin.flush()
    assert client.read()["error"]["code"] == "invalid_request"
    assert client.request("library.state")["result"]["state"] == "no_library"


def test_oversized_multibyte_line_is_drained_then_valid_request_recovers(client):
    client.process.stdin.write(("é" * 40000 + "\n").encode())
    client.process.stdin.flush()
    assert client.read()["error"]["code"] == "message_too_large"
    assert client.request("library.state")["ok"]


def test_control_burst_above_sixteen_frames_fails_closed(client):
    frames = [
        json.dumps({"id": str(i), "token": TOKEN, "method": "library.state"}) for i in range(17)
    ]
    client.process.stdin.write(("\n".join(frames) + "\n").encode())
    client.process.stdin.flush()
    assert client.process.wait(timeout=4) == 4


def test_stdout_backpressure_does_not_stop_idle_tick():
    from playmemories_photo_manager.desktop.transport import PipePump

    source_r, source_w = os.pipe()
    sink_r, sink_w = os.pipe()
    source, sink = os.fdopen(source_r, "rb"), os.fdopen(sink_w, "wb")
    pump = PipePump(source, sink)
    calls = 0

    class End(Exception):
        pass

    def tick():
        nonlocal calls
        calls += 1
        if calls == 12:
            raise End

    try:
        pump.write("x" * (256 * 1024))
        with pytest.raises(End):
            list(pump.lines(tick))
        assert calls == 12 and pump.output
    finally:
        pump.close()
        source.close()
        sink.close()
        os.close(source_w)
        os.close(sink_r)


def test_eof_during_preparation_cleans_up_before_exit(client, tmp_path):
    setup(client, tmp_path, 100)
    client.process.stdin.close()
    assert client.process.wait(timeout=5) == 0


def test_replayed_admission_and_busy_selection_do_not_touch_filesystem(tmp_path, monkeypatch):
    from playmemories_photo_manager.catalog_ingestion.root_grants import RootGrantService
    from playmemories_photo_manager.library import LibrarySession

    root = tmp_path / "media"
    root.mkdir()
    with LibrarySession.create(tmp_path / "catalog") as session:
        service = RootGrantService(session, str(uuid4()), protected_paths=())
        scope = {"session_id": service.session_id, "window_id": service.window_id}
        selected = service.select(
            scope | {"path": str(root), "recursive": True, "identity_reviewed": True}
        )
        params = scope | {
            "root_grant_id": selected["root_grant_id"],
            "recursive": True,
            "client_request_id": str(uuid4()),
        }
        admitted = service.prepare(params)
        monkeypatch.setattr(
            service,
            "_catalog_check",
            lambda: pytest.fail("no filesystem validation for admitted replay"),
        )
        try:
            assert service.prepare(params)["operation_id"] == admitted["operation_id"]
        finally:
            assert service.close()


def complete_proposal(client, scope, operation):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        status = client.request("ingestion.status", scope | {"operation_id": operation})["result"]
        if status["state"] == "completed":
            return status["proposal_id"]
        time.sleep(0.01)
    pytest.fail("preparation timed out")


def test_authenticated_vertical_flow_apply_refresh_reopen_and_no_duplicate_admission(
    client, tmp_path
):
    root, scope, operation = setup(client, tmp_path, 3)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
    proposal = complete_proposal(client, scope, operation)
    page = client.request(
        "ingestion.page", scope | {"proposal_id": proposal, "cursor": None, "page_size": 50}
    )["result"]
    assert all(item["selectable"] for item in page["items"])
    request = scope | {
        "proposal_id": proposal,
        "candidate_ids": [item["candidate_id"] for item in page["items"][:2]],
        "client_request_id": str(uuid4()),
    }
    result = client.request("ingestion.apply", request)
    assert result["ok"], result
    command = result["result"]["command_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.request("ingestion.application_status", scope | {"command_id": command})
        assert result["ok"], result
        if result["result"]["state"] in ("completed", "outcome_unknown"):
            break
        time.sleep(0.01)
    assert result["result"]["result"]["status"] == "applied", result
    assert client.request("ingestion.apply", request)["result"] == result["result"]
    gallery = client.request("gallery.list", {"session_id": scope["session_id"], "page_size": 24})
    assert len(gallery["result"]["items"]) == 2, gallery
    ids = {item["asset_id"] for item in gallery["result"]["items"]}
    assert str(root) not in json.dumps(result)
    assert client.request("library.close", {"session_id": scope["session_id"]})["ok"]
    opened = client.request(
        "library.open", {"path": str(tmp_path / "catalog.sqlite3"), "library_handle": str(uuid4())}
    )
    new_session = opened["result"]["session"]["session_id"]
    assert new_session != scope["session_id"]
    reopened = client.request("gallery.list", {"session_id": new_session, "page_size": 24})
    assert {item["asset_id"] for item in reopened["result"]["items"]} == ids
    assert (
        client.request("ingestion.application_status", scope | {"command_id": command})["error"][
            "code"
        ]
        == "stale_session"
    )
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()} == before


def test_apply_route_rejects_paths_and_cross_window_without_admission(client, tmp_path):
    _, scope, operation = setup(client, tmp_path)
    proposal = complete_proposal(client, scope, operation)
    request = scope | {
        "proposal_id": proposal,
        "candidate_ids": [],
        "client_request_id": str(uuid4()),
    }
    assert (
        client.request("ingestion.apply", request | {"path": "/untrusted"})["error"]["code"]
        == "invalid_request"
    )
    assert (
        client.request("ingestion.apply", request | {"window_id": str(uuid4())})["error"]["code"]
        == "stale_session"
    )


def test_multiformat_worker_calendar_and_image_jobs_through_authenticated_pipe(client, tmp_path):
    from PIL import Image

    root = tmp_path / "images"
    root.mkdir()
    Image.new("RGB", (80, 40), (20, 100, 180)).save(root / "synthetic.png")
    exif = Image.Exif()
    exif[34665] = {36867: "2024:02:29 23:30:00", 36881: "-03:00"}
    Image.new("RGB", (80, 40), (180, 100, 20)).save(
        root / "progressive.jpg", progressive=True, exif=exif
    )
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    created = client.request(
        "library.create",
        {"path": str(tmp_path / "catalog.sqlite3"), "library_handle": str(uuid4())},
    )
    scope = {"session_id": created["result"]["session"]["session_id"], "window_id": str(uuid4())}
    grant = client.request(
        "ingestion.select_root",
        scope | {"path": str(root), "recursive": True, "identity_reviewed": True},
    )["result"]["root_grant_id"]
    operation = client.request(
        "ingestion.prepare",
        scope | {"root_grant_id": grant, "recursive": True, "client_request_id": str(uuid4())},
    )["result"]["operation_id"]
    proposal = complete_proposal(client, scope, operation)
    page = client.request(
        "ingestion.page", scope | {"proposal_id": proposal, "cursor": None, "page_size": 50}
    )["result"]
    assert all(item["selectable"] for item in page["items"])
    command = client.request(
        "ingestion.apply",
        scope
        | {
            "proposal_id": proposal,
            "candidate_ids": [item["candidate_id"] for item in page["items"]],
            "client_request_id": str(uuid4()),
        },
    )["result"]["command_id"]
    deadline = time.monotonic() + 8
    while True:
        result = client.request("ingestion.application_status", scope | {"command_id": command})[
            "result"
        ]
        if result["state"] == "completed":
            break
        assert result["state"] != "outcome_unknown"
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert result["result"]["status"] == "applied"
    context = {"session_id": scope["session_id"]}
    calendar = client.request("calendar.summary", context | {"period": "2024-02"})
    assert calendar["result"]["buckets"] == [["2024-02-29", 1]]
    assert calendar["result"]["undated"] == 1
    gallery = client.request("gallery.list", context | {"capture_period": "2024-02-29"})["result"]
    asset_id = gallery["items"][0]["asset_id"]
    for method in ("thumbnail.get", "preview.get"):
        deadline = time.monotonic() + 8
        while True:
            response = client.request(method, context | {"asset_id": asset_id})
            assert response["ok"], response
            image = response["result"]
            if image and image.get("status") != "pending":
                break
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert image["synthetic"] is False
        assert str(root) not in json.dumps(response)
        assert (
            client.request(method, context | {"asset_id": asset_id, "path": str(root)})["error"][
                "code"
            ]
            == "invalid_request"
        )
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    assert (
        client.request("calendar.summary", {"session_id": str(uuid4()), "period": None})["error"][
            "code"
        ]
        == "stale_session"
    )
