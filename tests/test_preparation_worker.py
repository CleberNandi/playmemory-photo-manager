"""Real disposable processes, synthetic catalogs/media, no desktop route enabled."""

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from uuid import uuid4

import pytest
from jpeg_fixtures import jpeg

from playmemories_photo_manager.catalog import Catalog, initialize_database
from playmemories_photo_manager.catalog_ingestion import preparation as module
from playmemories_photo_manager.catalog_ingestion.media import _mount_id
from playmemories_photo_manager.catalog_ingestion.preparation import (
    PreparationController,
    PreparationError,
    PreparationInput,
)


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    catalog = tmp_path / "catalog.sqlite3"
    connection = initialize_database(catalog)
    root_id = Catalog(connection).register_root("Synthetic", str(root)).id
    connection.close()
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        mount = _mount_id(fd)
    finally:
        os.close(fd)
    selected = PreparationInput(
        str(catalog),
        str(root),
        root_id,
        (catalog.stat().st_dev, catalog.stat().st_ino),
        (root.stat().st_dev, root.stat().st_ino),
        mount,
    )
    controller = PreparationController(str(uuid4()), str(uuid4()))
    yield controller, selected, root, catalog
    if not controller._closed:
        assert controller.shutdown()
    else:
        deadline = time.monotonic() + 3
        while controller.busy and time.monotonic() < deadline:
            controller.tick()
            time.sleep(0.01)
        assert not controller.busy


def finish(controller, timeout=8):
    deadline = time.monotonic() + timeout
    while controller.busy and time.monotonic() < deadline:
        controller.tick()
        time.sleep(0.01)
    assert not controller.busy, "worker cleanup did not complete within test deadline"
    return controller._current


def fake_worker(monkeypatch, program):
    original = subprocess.Popen

    def spawn(arguments, **kwargs):
        assert arguments[1:3] == [
            "-m",
            "playmemories_photo_manager.catalog_ingestion.preparation_worker",
        ]
        assert kwargs["close_fds"] is True and kwargs["shell"] is False
        return original([sys.executable, "-c", program, arguments[3]], **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", spawn)


IGNORE = """
import json,signal,sys,time
signal.signal(signal.SIGUSR1,signal.SIG_IGN)
signal.signal(signal.SIGTERM,signal.SIG_IGN)
print(json.dumps({'operation_id':sys.argv[1],'kind':'ready'}),flush=True)
while True: time.sleep(.1)
"""


def ready(controller):
    deadline = time.monotonic() + 5
    while not controller._ready and controller.busy and time.monotonic() < deadline:
        controller.tick()
        time.sleep(0.01)
    assert controller._ready


def test_real_worker_result_is_validated_reaped_private_and_paginated(setup, monkeypatch):
    controller, selected, root, catalog = setup
    for i in range(3):
        (root / f"{i}.jpg").write_bytes(jpeg())
    before = catalog.read_bytes()
    monkeypatch.setenv("PLAYMEMORIES_BRIDGE_TOKEN", "synthetic-secret-never-inherited")
    admission = controller.start(selected, str(uuid4()))
    process = controller._process
    assert admission["state"] == "queued"
    assert str(root) not in json.dumps(admission)
    result = finish(controller)
    assert result.state == "completed", result
    assert process.returncode == 0
    with pytest.raises(ChildProcessError):
        os.waitpid(process.pid, os.WNOHANG)  # Popen.poll has already reaped it.
    page = controller.page(
        controller.session_id, controller.window_id, result.proposal_id, page_size=2
    )
    assert [item["relative_path"] for item in page["items"]] == ["0.jpg", "1.jpg"]
    assert len(page["next_cursor"]) == 64
    assert page == controller.page(
        controller.session_id, controller.window_id, result.proposal_id, page_size=2
    )
    last = controller.page(
        controller.session_id, controller.window_id, result.proposal_id, page["next_cursor"], 2
    )
    assert last["items"][0]["relative_path"] == "2.jpg" and last["next_cursor"] is None
    assert "fingerprint" not in json.dumps(page)
    assert str(root) not in json.dumps(page)
    assert catalog.read_bytes() == before


def test_admission_busy_dedup_and_scope(setup):
    controller, selected, _root, _catalog = setup
    request_id = str(uuid4())
    first = controller.start(selected, request_id)
    assert controller.start(selected, request_id) == first
    with pytest.raises(PreparationError, match="busy"):
        controller.start(selected, str(uuid4()))
    with pytest.raises(PreparationError, match="invalid_request"):
        controller.start(replace(selected, mount_id=selected.mount_id + 1), request_id)
    for session, window in (
        (None, None),
        (str(uuid4()), controller.window_id),
        (controller.session_id, str(uuid4())),
    ):
        with pytest.raises(PreparationError, match="stale_session"):
            controller.status(session, window, first["operation_id"])
    finish(controller)
    with pytest.raises(PreparationError, match="invalid_request"):
        controller.page(
            controller.session_id, controller.window_id, controller._current.proposal_id, "forged"
        )


def test_cancel_before_publication_discards_and_reaps(setup):
    controller, selected, _root, _catalog = setup
    job = controller.start(selected, str(uuid4()))
    response = controller.cancel(controller.session_id, controller.window_id, job["operation_id"])
    assert response["cancel_effect"] == "accepted"
    assert response["job"]["state"] == "cancelling"
    assert controller._published is None
    assert finish(controller).state == "cancelled"
    assert (
        controller.cancel(controller.session_id, controller.window_id, job["operation_id"])[
            "cancel_effect"
        ]
        == "too_late"
    )


def test_forced_cancel_does_not_release_slot_until_reap(setup, monkeypatch):
    controller, selected, _root, _catalog = setup
    fake_worker(monkeypatch, IGNORE)
    job = controller.start(selected, str(uuid4()))
    ready(controller)
    process = controller._process
    controller.cancel(controller.session_id, controller.window_id, job["operation_id"])
    assert controller.busy
    assert controller.shutdown(timeout=0) is False
    assert controller.busy and controller._current.state == "cancelling"
    result = finish(controller)
    assert result.state == "cancelled"
    assert process.returncode == -signal.SIGKILL
    assert not controller.busy


@pytest.mark.parametrize("reason", ["startup_timeout", "execution_timeout", "resource_limit"])
def test_external_deadline_and_rss_fail_closed(setup, monkeypatch, reason):
    controller, selected, _root, _catalog = setup
    fake_worker(monkeypatch, IGNORE)
    controller.start(selected, str(uuid4()))
    if reason != "startup_timeout":
        ready(controller)
    if reason == "startup_timeout":
        controller._started -= 6
    elif reason == "execution_timeout":
        controller._started -= 31
    else:
        monkeypatch.setattr(module, "_read_rss", lambda _pid: 257 * 1024 * 1024)
        controller._last_monitor -= 0.1
    result = finish(controller)
    assert result.state == "failed"
    assert result.terminal_reason == reason
    assert controller._published is None


def test_monitor_failure_rejects_admission_or_cancels_live_worker(setup, monkeypatch):
    controller, selected, _root, _catalog = setup
    fake_worker(monkeypatch, IGNORE)
    controller.start(selected, str(uuid4()))
    ready(controller)

    def broken(_pid):
        raise OSError

    monkeypatch.setattr(module, "_read_rss", broken)
    with pytest.raises(PreparationError, match="unavailable"):
        PreparationController(str(uuid4()), str(uuid4()))
    controller._last_monitor -= 0.1
    assert finish(controller).terminal_reason == "protocol_failure"


def test_crash_has_no_proposal_and_no_live_worker(setup, monkeypatch):
    controller, selected, _root, _catalog = setup
    fake_worker(monkeypatch, "import os; os._exit(7)")
    controller.start(selected, str(uuid4()))
    assert finish(controller).terminal_reason == "worker_crash"


@pytest.mark.parametrize(
    "program",
    [
        "print('x'*65537,flush=True)",
        'print(\'{"kind":"ready","kind":"ready"}\',flush=True)',
        'print(\'{"operation_id":"wrong","kind":"ready"}\',flush=True)',
    ],
)
def test_bad_worker_protocol_is_not_published(setup, monkeypatch, program):
    controller, selected, _root, _catalog = setup
    fake_worker(monkeypatch, program)
    controller.start(selected, str(uuid4()))
    assert finish(controller).terminal_reason == "protocol_failure"


def test_root_or_catalog_replacement_is_rejected_in_worker(setup):
    controller, selected, root, _catalog = setup
    root.rename(root.with_name("retained"))
    root.mkdir()
    controller.start(selected, str(uuid4()))
    assert finish(controller).terminal_reason == "root_changed"
    controller.start(replace(selected, catalog_identity=(0, 0)), str(uuid4()))
    assert finish(controller).terminal_reason == "root_changed"


def test_huge_tree_is_not_completed(setup):
    controller, selected, root, _catalog = setup
    for i in range(2001):
        (root / str(i)).touch()
    controller.start(selected, str(uuid4()))
    assert finish(controller).terminal_reason == "resource_limit"


def test_worker_environment_and_foreign_descriptors_are_not_inherited(setup, monkeypatch):
    controller, selected, _root, _catalog = setup
    fake_worker(monkeypatch, IGNORE)
    monkeypatch.setenv("PLAYMEMORIES_BRIDGE_TOKEN", "synthetic-not-for-child")
    fd = os.open("/dev/null", os.O_RDONLY)
    os.set_inheritable(fd, True)
    try:
        controller.start(selected, str(uuid4()))
        ready(controller)
        with open(f"/proc/{controller._monitor_pid}/environ", "rb") as source:
            environment = source.read()
        assert b"PLAYMEMORIES_BRIDGE_TOKEN" not in environment
        assert b"synthetic-not-for-child" not in environment
        # The numeric descriptor might be reused by Python; the original /dev/null handle is absent.
        links = []
        for name in os.listdir(f"/proc/{controller._monitor_pid}/fd"):
            links.append(os.readlink(f"/proc/{controller._monitor_pid}/fd/{name}"))
        assert links.count("/dev/null") <= 1  # Only deliberately redirected stderr.
    finally:
        os.close(fd)


def test_spawn_failure_is_sanitized_without_admitting_a_job(setup, monkeypatch):
    controller, selected, _root, _catalog = setup

    def failed(*_args, **_kwargs):
        raise OSError("synthetic private path")

    monkeypatch.setattr(module.subprocess, "Popen", failed)
    with pytest.raises(PreparationError, match="^unavailable$"):
        controller.start(selected, str(uuid4()))
    assert not controller.busy and not controller._admissions


def test_pipe_setup_failure_retains_slot_until_reaped(setup, monkeypatch):
    controller, selected, _root, _catalog = setup
    fake_worker(monkeypatch, IGNORE)

    def failed(*_args):
        raise OSError

    monkeypatch.setattr(module.os, "set_blocking", failed)
    controller.start(selected, str(uuid4()))
    assert controller.busy
    assert finish(controller).terminal_reason == "protocol_failure"


def test_real_rss_limit_is_detected_and_worker_reaped(setup, monkeypatch):
    controller, selected, _root, _catalog = setup
    # Hold the allocation, giving the external monitor time to sample it.
    fake_worker(
        monkeypatch,
        IGNORE.replace("while True:", "allocation = bytearray(270 * 1024 * 1024)\nwhile True:"),
    )
    controller.start(selected, str(uuid4()))
    result = finish(controller)
    assert result.terminal_reason == "resource_limit"
    assert controller.peak_worker_rss > 256 * 1024 * 1024
    assert controller.max_monitor_gap < 0.5


@pytest.mark.parametrize(
    "payload",
    [
        b'{"type":"os.system","fields":{}}',
        b'{"datetime":"2026-01-01","datetime":"2026-02-02"}',
        b'{"enum":"os.system","value":"x"}',
        b"{}",
        b"[]",
        b"0",
        b"NaN",
    ],
)
def test_private_wire_rejects_untrusted_tags_and_non_proposals(payload):
    from playmemories_photo_manager.catalog_ingestion.worker_wire import decode_result

    with pytest.raises((ValueError, KeyError, TypeError)):
        decode_result(payload)


def test_result_wire_recomputes_fingerprint_instead_of_trusting_worker(setup):
    from playmemories_photo_manager.catalog_ingestion.worker_wire import (
        decode_result,
        encode_result,
    )

    controller, selected, root, _catalog = setup
    (root / "synthetic.jpg").write_bytes(jpeg())
    controller.start(selected, str(uuid4()))
    assert finish(controller).state == "completed"
    original = controller._published
    assert decode_result(encode_result(original)) == original
    forged = replace(original, scope_fingerprint="0" * 64)
    with pytest.raises(ValueError):
        decode_result(encode_result(forged))


def test_borrowed_root_descriptor_is_preserved_and_mount_guard_refuses(setup):
    from playmemories_photo_manager.scanner import ScanOptions, ScanScopeChangedError, scan

    _controller, selected, root, _catalog = setup
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert scan(root, ScanOptions(mount_id=selected.mount_id), root_fd=fd).is_complete
        assert os.fstat(fd).st_ino == root.stat().st_ino
        with pytest.raises(ScanScopeChangedError):
            scan(root, ScanOptions(mount_id=selected.mount_id + 1), root_fd=fd)
        assert os.fstat(fd).st_ino == root.stat().st_ino
    finally:
        os.close(fd)


def test_controller_process_death_kills_worker_and_subreaper_collects_it():
    # An isolated grandparent owns the subreaper setting; the pytest process is unchanged.
    helper = """
import os, subprocess, sys
worker = subprocess.Popen([
    sys.executable, '-m', 'playmemories_photo_manager.catalog_ingestion.preparation_worker',
    sys.argv[1], str(os.getpid())], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL, close_fds=True)
assert b'"kind":"ready"' in worker.stdout.readline()
print(worker.pid, flush=True)
os._exit(0)
"""
    grandparent = """
import ctypes, os, signal, subprocess, sys, time
assert ctypes.CDLL(None).prctl(36, 1, 0, 0, 0) == 0
parent = subprocess.run([sys.executable, '-c', sys.argv[1], sys.argv[2]],
    stdout=subprocess.PIPE, check=True, timeout=5)
worker_pid = int(parent.stdout)
deadline = time.monotonic() + 3
while time.monotonic() < deadline:
    pid, status = os.waitpid(worker_pid, os.WNOHANG)
    if pid:
        assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
        break
    time.sleep(.01)
else:
    os.kill(worker_pid, signal.SIGKILL)
    os.waitpid(worker_pid, 0)
    raise AssertionError('parent death did not kill worker')
"""
    subprocess.run(
        [sys.executable, "-c", grandparent, helper, str(uuid4())], check=True, timeout=10
    )
