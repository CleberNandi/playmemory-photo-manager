import os
from dataclasses import replace
from uuid import uuid4

import pytest
from jpeg_fixtures import jpeg

from playmemories_photo_manager.catalog import Catalog, initialize_database
from playmemories_photo_manager.catalog_ingestion import (
    IngestionAuthorizationError,
    MediaPreparationError,
    MediaVerificationCancelled,
    ProposalResourceLimitError,
    SnapshotLimits,
    authorize_ingestion,
    capture_catalog_snapshot,
    classify_media,
    media,
    prepare_from_snapshot,
    scope_catalogable_proposal,
    scoping,
)
from playmemories_photo_manager.change_planning import PlanningContext, PlanStatus
from playmemories_photo_manager.scanner import ScanLimits, ScanOptions, scan


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    path = tmp_path / "catalog.sqlite3"
    connection = initialize_database(path)
    registered = Catalog(connection).register_root("Synthetic", str(root))
    connection.close()
    return root, path, registered.id


def proposal(library):
    root, path, root_id = library
    snapshot = capture_catalog_snapshot(path, root_id, limits=SnapshotLimits())
    observed = scan(root, ScanOptions(limits=ScanLimits()))
    context = PlanningContext(root_id, str(root), str(root), observed.scope)
    return prepare_from_snapshot(snapshot, observed, context)


def test_nested_jpeg_and_exclusions_preserve_full_original_plan(library):
    root, path, root_id = library
    (root / "nested").mkdir()
    (root / "nested" / "IMAGE.JPEG").write_bytes(jpeg(3))
    (root / "fake.jpg").write_text("not a JPEG")
    (root / "notes.txt").write_text("not read")
    (root / "link.jpg").symlink_to("nested/IMAGE.JPEG")
    os.mkfifo(root / "pipe")
    original = proposal(library)
    before = path.read_bytes()
    eligibility = classify_media(original.scan_result, root_id)
    scoped = scope_catalogable_proposal(original, eligibility)
    assert scoped.original is original
    assert original.plan.status is PlanStatus.INCONCLUSIVE
    assert len(original.scan_result.entries) == len(eligibility) == 6
    assert [r.relative_path for r in scoped.eligible_candidates] == ["nested/IMAGE.JPEG"]
    assert len(scoped.exclusions) == 5
    with pytest.raises(IngestionAuthorizationError):
        authorize_ingestion(original.plan, ())  # Legacy gate remains strict about directories.
    assert path.read_bytes() == before
    assert scope_catalogable_proposal(original, tuple(reversed(eligibility))) == scoped


def test_empty_tree_produces_empty_projection(library):
    _root, _path, root_id = library
    original = proposal(library)
    scoped = scope_catalogable_proposal(original, classify_media(original.scan_result, root_id))
    assert scoped.eligible_candidates == scoped.exclusions == ()


def test_nonregular_and_unsupported_extension_do_not_open_contents(library, monkeypatch):
    root, _path, root_id = library
    (root / "ignored.png").write_bytes(b"not read")
    (root / "link.jpg").symlink_to("ignored.png")
    os.mkfifo(root / "pipe.jpg")
    original = proposal(library)
    monkeypatch.setattr(media, "_verify_file", lambda *_a: pytest.fail("content opened"))
    result = classify_media(original.scan_result, root_id)
    assert {r.reason for r in result} == {"unsupported_extension", "not_regular_file"}
    assert all(r.fingerprint is None for r in result)


@pytest.mark.parametrize("mutation", ["size", "inode", "mtime", "symlink", "missing"])
def test_file_changes_after_scan_block_entire_projection(library, mutation):
    root, _path, root_id = library
    path = root / "image.jpg"
    path.write_bytes(jpeg())
    original = proposal(library)
    if mutation == "size":
        path.write_bytes(jpeg() + b"changed")
    elif mutation == "mtime":
        os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1))
    else:
        path.rename(root / "retained")
        if mutation == "inode":
            path.write_bytes(jpeg())
        elif mutation == "symlink":
            path.symlink_to("retained")
    result = classify_media(original.scan_result, root_id)
    assert result[0].state == "failed"
    with pytest.raises(IngestionAuthorizationError):
        scope_catalogable_proposal(original, result)


def test_change_during_parse_wins_over_format_failure_and_closes_fds(library, monkeypatch):
    root, _path, root_id = library
    path = root / "image.jpg"
    path.write_bytes(jpeg())
    original = proposal(library)
    inspect = media.inspect_jpeg

    def mutate(source, size, **kwargs):
        path.write_bytes(b"modified")
        return inspect(source, size, **kwargs)

    monkeypatch.setattr(media, "inspect_jpeg", mutate)
    before = set(os.listdir("/proc/self/fd"))
    result = classify_media(original.scan_result, root_id)
    assert result[0].reason == "entry_changed_during_verification"
    assert result[0].state == "failed"
    assert set(os.listdir("/proc/self/fd")) == before


def test_replaced_root_and_symlink_ancestor_are_rejected(library):
    root, _path, root_id = library
    (root / "image.jpg").write_bytes(jpeg())
    original = proposal(library)
    root.rename(root.with_name("retained"))
    root.mkdir()
    with pytest.raises(MediaPreparationError, match="root_changed"):
        classify_media(original.scan_result, root_id)
    root.rmdir()
    root.symlink_to(root.with_name("retained"), target_is_directory=True)
    with pytest.raises(MediaPreparationError, match="root_changed"):
        classify_media(original.scan_result, root_id)


def test_cancellation_reaps_local_descriptors(library):
    root, _path, root_id = library
    (root / "image.jpg").write_bytes(jpeg())
    original = proposal(library)
    before = set(os.listdir("/proc/self/fd"))
    with pytest.raises(MediaVerificationCancelled):
        classify_media(original.scan_result, root_id, cancellation_requested=lambda: True)
    assert set(os.listdir("/proc/self/fd")) == before


def test_deadline_is_failed_not_format_exclusion(library, monkeypatch):
    root, _path, root_id = library
    (root / "image.jpg").write_bytes(jpeg())
    original = proposal(library)

    def timeout(*_a, **_k):
        raise media._VerificationTimeout

    monkeypatch.setattr(media, "inspect_jpeg", timeout)
    result = classify_media(original.scan_result, root_id)
    assert result[0].state == "failed"
    assert result[0].reason == "verification_timeout"
    with pytest.raises(IngestionAuthorizationError):
        scope_catalogable_proposal(original, result)


def test_changed_mount_is_rejected_even_with_same_device(library, monkeypatch):
    root, _path, root_id = library
    (root / "image.jpg").write_bytes(jpeg())
    original = proposal(library)
    mount_id = media._mount_id

    def different_for_regular_file(fd):
        import stat

        return mount_id(fd) + int(stat.S_ISREG(os.fstat(fd).st_mode))

    monkeypatch.setattr(media, "_mount_id", different_for_regular_file)
    result = classify_media(original.scan_result, root_id)
    assert result[0].reason == "entry_changed_during_verification"


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "duplicate", "id", "run", "profile", "fp", "failed", "observation"],
)
def test_scope_rejects_mismatched_or_incomplete_evidence(library, mutation):
    root, _path, root_id = library
    (root / "image.jpg").write_bytes(jpeg())
    original = proposal(library)
    result = classify_media(original.scan_result, root_id)
    first = result[0]
    if mutation == "missing":
        result = ()
    elif mutation in ("extra", "duplicate"):
        result += (first,)
    else:
        changes = {
            "id": {"candidate_id": "bad"},
            "run": {"candidate": replace(first.candidate, run_id=str(uuid4()))},
            "profile": {"profile": "unsupported"},
            "fp": {"fingerprint": None},
            "failed": {"state": "failed", "reason": "read_failed"},
            "observation": {"observation": replace(first.observation, byte_size=999)},
        }
        result = (replace(first, **changes[mutation]),)
    with pytest.raises(IngestionAuthorizationError):
        scope_catalogable_proposal(original, result)


def test_changed_original_plan_and_nonrecursive_coverage_never_scoped(library):
    root, _path, root_id = library
    (root / "image.jpg").write_bytes(jpeg())
    original = proposal(library)
    eligibility = classify_media(original.scan_result, root_id)
    with pytest.raises(IngestionAuthorizationError):
        scope_catalogable_proposal(
            replace(original, plan=replace(original.plan, changes=())), eligibility
        )
    nonrecursive = scan(root, ScanOptions(recursive=False, limits=ScanLimits()))
    with pytest.raises(MediaPreparationError):
        classify_media(nonrecursive, root_id)


def test_candidate_identity_is_opaque_and_fingerprint_covers_it(library):
    root, _path, root_id = library
    (root / "image.jpg").write_bytes(jpeg())
    original = proposal(library)
    eligibility = classify_media(original.scan_result, root_id)
    first = scope_catalogable_proposal(original, eligibility)
    changed = (replace(eligibility[0], candidate_id=str(uuid4())),)
    second = scope_catalogable_proposal(original, changed)
    assert first.scope_fingerprint != second.scope_fingerprint
    assert first.eligible_candidates == second.eligible_candidates


def test_scope_rejects_duplicate_ids_even_with_distinct_valid_paths(library):
    root, _path, root_id = library
    for name in ("a.jpg", "b.jpg"):
        (root / name).write_bytes(jpeg())
    original = proposal(library)
    first, second = classify_media(original.scan_result, root_id)
    with pytest.raises(IngestionAuthorizationError):
        scope_catalogable_proposal(
            original, (first, replace(second, candidate_id=first.candidate_id))
        )


def test_scope_budget_and_metadata_tampering_are_rejected(library, monkeypatch):
    root, _path, root_id = library
    (root / "image.jpg").write_bytes(jpeg())
    original = proposal(library)
    result = classify_media(original.scan_result, root_id)
    forged = replace(
        result[0],
        state="excluded",
        reason="unsupported_extension",
        fingerprint=None,
        detected_format=None,
    )
    with pytest.raises(IngestionAuthorizationError):
        scope_catalogable_proposal(original, (forged,))
    monkeypatch.setattr(scoping, "MAX_PROPOSAL_BYTES", 1024)
    with pytest.raises(ProposalResourceLimitError, match="resource_limit"):
        scope_catalogable_proposal(original, result)


def test_unreadable_jpeg_blocks_and_does_not_leak_descriptors(library, monkeypatch):
    root, _path, root_id = library
    (root / "image.jpg").write_bytes(jpeg())
    original = proposal(library)
    open_original = media.os.open

    def denied(path, *args, **kwargs):
        if path == "image.jpg":
            raise PermissionError
        return open_original(path, *args, **kwargs)

    before = set(os.listdir("/proc/self/fd"))
    monkeypatch.setattr(media.os, "open", denied)
    result = classify_media(original.scan_result, root_id)
    assert result[0].state == "failed"
    assert result[0].reason == "read_failed"
    assert set(os.listdir("/proc/self/fd")) == before


@pytest.mark.parametrize("name", ["directory", "ignored.png"])
def test_mount_crossing_for_excluded_entries_is_not_hidden(library, monkeypatch, name):
    import stat

    root, _path, root_id = library
    if name == "directory":
        (root / name).mkdir()
    else:
        (root / name).write_bytes(b"not read")
    original = proposal(library)
    mount_id = media._mount_id

    def changed_mount(fd):
        info = os.fstat(fd)
        if name == "directory":
            different = info.st_ino == (root / name).stat().st_ino
        else:
            different = stat.S_ISREG(info.st_mode)
        return mount_id(fd) + int(different)

    monkeypatch.setattr(media, "_mount_id", changed_mount)
    with pytest.raises(MediaPreparationError, match="root_changed"):
        classify_media(original.scan_result, root_id)
