import os
from dataclasses import replace

import pytest
from jpeg_fixtures import jpeg

from playmemories_photo_manager.catalog import Catalog, initialize_database
from playmemories_photo_manager.catalog_ingestion import (
    IngestionAuthorizationError,
    MediaVerificationCancelled,
    ScopedPreflightError,
    SnapshotLimits,
    authorize_scoped_ingestion,
    capture_catalog_snapshot,
    classify_media,
    preflight_scoped_ingestion,
    prepare_from_snapshot,
    scope_catalogable_proposal,
    scoped_preflight,
)
from playmemories_photo_manager.catalog_ingestion.media import _mount_id
from playmemories_photo_manager.change_planning import PlanningContext
from playmemories_photo_manager.scanner import ScanLimits, ScanOptions, scan


@pytest.fixture
def batch(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    (root / "nested").mkdir()
    (root / "nested" / "a.jpg").write_bytes(jpeg(3))
    (root / "b.jpg").write_bytes(jpeg(1))
    (root / "notes.txt").write_text("synthetic excluded content")
    path = tmp_path / "catalog.sqlite3"
    connection = initialize_database(path)
    registered = Catalog(connection).register_root("Synthetic", str(root))
    connection.close()
    observed = scan(root, ScanOptions(limits=ScanLimits()))
    original = prepare_from_snapshot(
        capture_catalog_snapshot(path, registered.id, limits=SnapshotLimits()),
        observed,
        PlanningContext(registered.id, str(root), str(root), observed.scope),
    )
    scoped = scope_catalogable_proposal(original, classify_media(observed, registered.id))
    identifier = next(
        item.candidate_id
        for item in scoped.eligibilities
        if item.candidate.relative_path == "nested/a.jpg"
    )
    auth = authorize_scoped_ingestion(scoped, (identifier,))
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        mount = _mount_id(fd)
    finally:
        os.close(fd)
    return scoped, auth, mount, root, path


def test_held_preflight_preserves_originals_and_catalog_and_expires_on_exit(batch):
    scoped, auth, mount, root, path = batch
    paths = [path, *(p for p in root.rglob("*") if p.is_file())]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    with preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount) as checked:
        checked.check_root()
        assert checked.authorization == auth
    with pytest.raises(ScopedPreflightError, match="preflight_closed"):
        checked.check_root()
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths} == before


@pytest.mark.parametrize(
    "change", ["write", "unlink", "replace", "symlink", "fifo", "parent_symlink"]
)
def test_detectable_selected_changes_block_entire_preflight(batch, change):
    scoped, auth, mount, root, _ = batch
    selected = root / "nested" / "a.jpg"
    if change == "write":
        original = selected.stat()
        selected.write_bytes(jpeg(1))
        os.utime(selected, ns=(original.st_atime_ns, original.st_mtime_ns))
    elif change == "parent_symlink":
        (root / "nested").rename(root / "old-nested")
        (root / "nested").symlink_to(root / "old-nested", target_is_directory=True)
    else:
        selected.unlink()
        if change == "replace":
            selected.write_bytes(jpeg(3))
        if change == "symlink":
            selected.symlink_to(root / "b.jpg")
        if change == "fifo":
            os.mkfifo(selected)
    with (
        pytest.raises(ScopedPreflightError, match="source_changed"),
        preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount),
    ):
        pytest.fail("changed file admitted")


def test_root_substitution_before_and_after_preflight_is_rejected(batch):
    scoped, auth, mount, root, _ = batch
    with preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount) as checked:
        root.rename(root.with_name("old-media"))
        root.mkdir()
        with pytest.raises(ScopedPreflightError, match="source_changed"):
            checked.check_root()
    with (
        pytest.raises(ScopedPreflightError, match="source_changed"),
        preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount),
    ):
        pass


def test_unselected_files_are_not_reopened(batch, monkeypatch):
    scoped, auth, mount, root, _ = batch
    (root / "b.jpg").unlink()
    (root / "notes.txt").write_text("changed excluded file")
    verify = scoped_preflight._verify_file
    seen = []

    def record(fd, binding, observation, checkpoint, capture=None):
        seen.append(observation.relative_path)
        return verify(fd, binding, observation, checkpoint, capture)

    monkeypatch.setattr(scoped_preflight, "_verify_file", record)
    with preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount):
        pass
    assert seen == ["nested/a.jpg"]


@pytest.mark.parametrize("binding", [True, None, -1, 0])
def test_invalid_mount_binding_fails_closed(batch, binding):
    scoped, auth, _, _, _ = batch
    with (
        pytest.raises(ScopedPreflightError, match="invalid_mount_binding"),
        preflight_scoped_ingestion(scoped, auth, expected_root_mount=binding),
    ):
        pass


def test_different_mount_identity_is_rejected(batch):
    scoped, auth, mount, _, _ = batch
    with (
        pytest.raises(ScopedPreflightError, match="source_changed"),
        preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount + 1),
    ):
        pass


def test_cancel_timeout_and_bad_consent_never_admit_batch(batch, monkeypatch):
    scoped, auth, mount, _, _ = batch
    with (
        pytest.raises(MediaVerificationCancelled),
        preflight_scoped_ingestion(
            scoped, auth, expected_root_mount=mount, cancellation_requested=lambda: True
        ),
    ):
        pass
    with (
        pytest.raises(IngestionAuthorizationError),
        preflight_scoped_ingestion(
            scoped, replace(auth, decision_fingerprint="forged"), expected_root_mount=mount
        ),
    ):
        pass
    clock = iter([0, 31])
    monkeypatch.setattr(scoped_preflight.time, "monotonic", lambda: next(clock))
    with (
        pytest.raises(ScopedPreflightError, match="verification_timeout"),
        preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount),
    ):
        pass


def test_releases_descriptors_on_success_failure_and_body_exception(batch):
    scoped, auth, mount, root, _ = batch
    from pathlib import Path

    before = set(os.listdir("/proc/self/fd"))
    for _ in range(3):
        with preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount):
            pass
        with (
            pytest.raises(ValueError, match="body"),
            preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount),
        ):
            raise ValueError("body")
    (root / "nested" / "a.jpg").unlink()
    with (
        pytest.raises(ScopedPreflightError),
        preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount),
    ):
        pass
    assert set(os.listdir(Path("/proc/self/fd"))) == before


def test_checks_live_path_mount_even_with_unchanged_held_descriptor(batch, monkeypatch):
    scoped, auth, mount, _, _ = batch
    with preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount) as checked:
        monkeypatch.setattr(
            scoped_preflight, "_mount_id", lambda fd: mount if fd == checked._root_fd else mount + 1
        )
        with pytest.raises(ScopedPreflightError, match="source_changed"):
            checked.check_root()


def test_empty_consent_does_not_read_media(batch, monkeypatch):
    scoped, _, mount, _, _ = batch
    auth = authorize_scoped_ingestion(scoped, ())
    monkeypatch.setattr(
        scoped_preflight, "_verify_file", lambda *_args: pytest.fail("file opened for empty choice")
    )
    with preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount):
        pass


def test_io_errors_are_sanitized_and_release_root(batch, monkeypatch):
    scoped, auth, mount, _, _ = batch
    before = set(os.listdir("/proc/self/fd"))

    def deny(*_args):
        raise PermissionError("private-path-do-not-publish")

    monkeypatch.setattr(scoped_preflight, "_verify_file", deny)
    with (
        pytest.raises(ScopedPreflightError) as error,
        preflight_scoped_ingestion(scoped, auth, expected_root_mount=mount),
    ):
        pass
    assert str(error.value) == "source_changed"
    assert set(os.listdir("/proc/self/fd")) == before
