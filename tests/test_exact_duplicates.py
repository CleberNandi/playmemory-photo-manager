from __future__ import annotations

import errno
import hashlib
import os
import sqlite3
import uuid
from pathlib import Path

import pytest

from playmemories_photo_manager.duplicates import (
    DuplicateCoverage,
    DuplicateIssueKind,
    find_exact_duplicates,
)


def _id() -> str:
    return str(uuid.uuid4())


def _root(database: sqlite3.Connection, path: Path, *, availability: str = "available") -> str:
    identifier = _id()
    database.execute(
        """INSERT INTO library_root(id, display_name, normalized_path, availability)
        VALUES (?, 'Synthetic', ?, ?)""",
        (identifier, str(path), availability),
    )
    return identifier


def _asset(database: sqlite3.Connection, *, digest: str | None = None) -> str:
    identifier = _id()
    database.execute(
        "INSERT INTO asset(id, kind, sha256, hash_state) VALUES (?, 'photo', ?, ?)",
        (identifier, digest, "verified" if digest else "absent"),
    )
    return identifier


def _location(
    database: sqlite3.Connection,
    asset_id: str,
    root_id: str,
    relative_path: str,
    *,
    path: Path | None = None,
    availability: str = "present",
    entry_type: str = "file",
    observed_size: int | None = None,
    observed_mtime_ns: int | None = None,
    filesystem_id: str | None = None,
) -> str:
    identifier = _id()
    if path is not None:
        info = path.stat()
        observed_size = info.st_size if observed_size is None else observed_size
        observed_mtime_ns = info.st_mtime_ns if observed_mtime_ns is None else observed_mtime_ns
        filesystem_id = filesystem_id or f"scanner:{info.st_dev}:{info.st_ino}"
    database.execute(
        """INSERT INTO file_location(
            id, asset_id, library_root_id, normalized_relative_path, entry_type,
            symlink_target, filesystem_id, observed_byte_size, observed_mtime_ns, availability
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            identifier,
            asset_id,
            root_id,
            relative_path,
            entry_type,
            "target" if entry_type == "symlink" else None,
            filesystem_id,
            observed_size,
            observed_mtime_ns,
            availability,
        ),
    )
    return identifier


def _write(root: Path, relative_path: str, content: bytes) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_exact_copies_preserve_distinct_assets_and_locations(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    first_asset, second_asset = _asset(database), _asset(database)
    first = _write(tmp_path, "a/one.jpg", b"same bytes")
    second = _write(tmp_path, "b/two.jpg", b"same bytes")
    first_location = _location(database, first_asset, root_id, "a/one.jpg", path=first)
    second_location = _location(database, second_asset, root_id, "b/two.jpg", path=second)

    result = find_exact_duplicates(database)

    assert result.coverage is DuplicateCoverage.COMPLETE
    assert result.issues == ()
    assert result.hashed_location_count == 2
    group = result.groups[0]
    assert group.sha256 == hashlib.sha256(b"same bytes").hexdigest()
    assert {member.asset_id for member in group.members} == {first_asset, second_asset}
    assert {member.location_id for member in group.members} == {
        first_location,
        second_location,
    }
    assert group.physical_copy_count == 2


def test_multiple_locations_of_one_asset_are_not_collapsed(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    asset_id = _asset(database)
    for name in ("one.jpg", "two.jpg"):
        path = _write(tmp_path, name, b"copy")
        _location(database, asset_id, root_id, name, path=path)

    group = find_exact_duplicates(database).groups[0]

    assert len(group.members) == 2
    assert {member.asset_id for member in group.members} == {asset_id}


@pytest.mark.skipif(os.name != "posix", reason="hardlinks require POSIX test semantics")
def test_hardlinks_remain_visible_and_are_distinguished(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    first = _write(tmp_path, "one.jpg", b"hardlinked")
    second = tmp_path / "two.jpg"
    os.link(first, second)
    for path in (first, second):
        _location(database, _asset(database), root_id, path.name, path=path)

    group = find_exact_duplicates(database).groups[0]

    assert len(group.members) == 2
    assert group.physical_copy_count == 1
    assert all(member.is_hardlinked for member in group.members)


def test_size_prefilter_skips_unique_sizes(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    for name, content in (("one.jpg", b"1"), ("two.jpg", b"22")):
        path = _write(tmp_path, name, content)
        _location(database, _asset(database), root_id, name, path=path)

    result = find_exact_duplicates(database)

    assert result.eligible_location_count == 2
    assert result.hashed_location_count == 0
    assert result.groups == ()


def test_same_size_different_content_is_not_a_group(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    for name, content in (("one.jpg", b"abc"), ("two.jpg", b"xyz")):
        path = _write(tmp_path, name, content)
        _location(database, _asset(database), root_id, name, path=path)

    result = find_exact_duplicates(database)

    assert result.hashed_location_count == 2
    assert result.groups == ()


def test_groups_and_members_are_deterministic(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    for name, content in (
        ("z.jpg", b"bbb"),
        ("y.jpg", b"aaa"),
        ("x.jpg", b"bbb"),
        ("w.jpg", b"aaa"),
    ):
        path = _write(tmp_path, name, content)
        _location(database, _asset(database), root_id, name, path=path)

    first = find_exact_duplicates(database)
    second = find_exact_duplicates(database)

    assert first == second
    assert [group.sha256 for group in first.groups] == sorted(
        group.sha256 for group in first.groups
    )
    assert all(
        [member.relative_path for member in group.members]
        == sorted(member.relative_path for member in group.members)
        for group in first.groups
    )


def test_symlink_location_is_explicit_and_never_followed(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    target = _write(tmp_path, "target.jpg", b"bytes")
    (tmp_path / "link.jpg").symlink_to(target)
    _location(database, _asset(database), root_id, "link.jpg", entry_type="symlink")

    result = find_exact_duplicates(database)

    assert result.coverage is DuplicateCoverage.PARTIAL
    assert [issue.kind for issue in result.issues] == [DuplicateIssueKind.SYMLINK_BLOCKED]


def test_catalogued_file_replaced_by_symlink_is_blocked(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    target = _write(tmp_path, "target.jpg", b"bytes")
    (tmp_path / "link.jpg").symlink_to(target)
    _location(database, _asset(database), root_id, "link.jpg")

    result = find_exact_duplicates(database)

    assert result.issues[0].kind is DuplicateIssueKind.SYMLINK_BLOCKED


def test_offline_root_and_missing_location_are_explicit(database, tmp_path: Path) -> None:
    offline = _root(database, tmp_path / "offline", availability="offline")
    available = _root(database, tmp_path)
    _location(database, _asset(database), offline, "one.jpg", availability="offline")
    _location(database, _asset(database), available, "two.jpg", availability="missing")

    result = find_exact_duplicates(database)

    assert {issue.kind for issue in result.issues} == {
        DuplicateIssueKind.ROOT_OFFLINE,
        DuplicateIssueKind.LOCATION_UNAVAILABLE,
    }


@pytest.mark.parametrize("attribute", ["size", "mtime", "identity"])
def test_changed_catalog_observation_is_explicit(database, tmp_path: Path, attribute: str) -> None:
    root_id = _root(database, tmp_path)
    path = _write(tmp_path, "one.jpg", b"content")
    kwargs = {"path": path}
    if attribute == "size":
        kwargs["observed_size"] = path.stat().st_size + 1
    elif attribute == "mtime":
        kwargs["observed_mtime_ns"] = path.stat().st_mtime_ns + 1
    else:
        kwargs["filesystem_id"] = "scanner:0:0"
    _location(database, _asset(database), root_id, "one.jpg", **kwargs)

    result = find_exact_duplicates(database)

    assert result.issues[0].kind is DuplicateIssueKind.FILE_CHANGED


def test_verified_hash_mismatch_is_reported_as_changed(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    wrong_digest = hashlib.sha256(b"old").hexdigest()
    for name in ("one.jpg", "two.jpg"):
        path = _write(tmp_path, name, b"new")
        _location(database, _asset(database, digest=wrong_digest), root_id, name, path=path)

    result = find_exact_duplicates(database)

    assert result.groups == ()
    assert {issue.kind for issue in result.issues} == {DuplicateIssueKind.FILE_CHANGED}


@pytest.mark.parametrize("relative_path", [".", "../escape.jpg", "a//b.jpg"])
def test_noncanonical_or_escaping_catalog_path_is_rejected(
    database, tmp_path: Path, relative_path: str
) -> None:
    root_id = _root(database, tmp_path)
    _location(database, _asset(database), root_id, relative_path)

    result = find_exact_duplicates(database)

    assert result.issues[0].kind is DuplicateIssueKind.INVALID_PATH


def test_symlink_in_location_ancestry_is_blocked(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    actual = tmp_path / "actual"
    actual.mkdir()
    (tmp_path / "alias").symlink_to(actual, target_is_directory=True)
    _location(database, _asset(database), root_id, "alias/one.jpg")

    result = find_exact_duplicates(database)

    assert result.issues[0].kind is DuplicateIssueKind.SYMLINK_BLOCKED


def test_regular_file_in_location_ancestry_is_read_failure(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    _write(tmp_path, "not-a-directory", b"bytes")
    _location(database, _asset(database), root_id, "not-a-directory/one.jpg")

    result = find_exact_duplicates(database)

    assert result.issues[0].kind is DuplicateIssueKind.READ_FAILED


def test_symlink_in_root_ancestry_is_rejected(database, tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    root_id = _root(database, alias)
    _location(database, _asset(database), root_id, "one.jpg")

    result = find_exact_duplicates(database)

    assert result.issues[0].kind is DuplicateIssueKind.INVALID_PATH


def test_missing_file_is_read_failure(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    _location(database, _asset(database), root_id, "missing.jpg")

    assert find_exact_duplicates(database).issues[0].kind is DuplicateIssueKind.READ_FAILED


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unavailable")
def test_non_regular_file_is_rejected_without_blocking(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    os.mkfifo(tmp_path / "pipe.jpg")
    _location(database, _asset(database), root_id, "pipe.jpg")

    assert find_exact_duplicates(database).issues[0].kind is DuplicateIssueKind.NOT_REGULAR_FILE


def test_change_during_hash_is_reported(database, tmp_path: Path, monkeypatch) -> None:
    root_id = _root(database, tmp_path)
    paths = []
    for name in ("one.jpg", "two.jpg"):
        path = _write(tmp_path, name, b"same")
        paths.append(path)
        _location(database, _asset(database), root_id, name, path=path)
    from playmemories_photo_manager.duplicates import detector

    original_read = detector.os.read
    changed = False

    def changing_read(file_descriptor: int, size: int) -> bytes:
        nonlocal changed
        chunk = original_read(file_descriptor, size)
        if chunk and not changed:
            changed = True
            paths[0].write_bytes(b"changed bytes")
        return chunk

    monkeypatch.setattr(detector.os, "read", changing_read)

    result = find_exact_duplicates(database)

    assert DuplicateIssueKind.FILE_CHANGED in {issue.kind for issue in result.issues}
    assert result.groups == ()


def test_read_error_during_hash_is_reported_as_read_failure(
    database, tmp_path: Path, monkeypatch
) -> None:
    root_id = _root(database, tmp_path)
    for name in ("one.jpg", "two.jpg"):
        path = _write(tmp_path, name, b"same")
        _location(database, _asset(database), root_id, name, path=path)
    from playmemories_photo_manager.duplicates import detector

    def failing_read(_file_descriptor: int, _size: int) -> bytes:
        raise OSError(errno.EIO, "injected read failure")

    monkeypatch.setattr(detector.os, "read", failing_read)

    result = find_exact_duplicates(database)

    assert {issue.kind for issue in result.issues} == {DuplicateIssueKind.READ_FAILED}
    assert result.groups == ()


def test_root_descriptor_is_closed_when_fstat_fails(database, tmp_path: Path, monkeypatch) -> None:
    root_id = _root(database, tmp_path)
    _location(database, _asset(database), root_id, "one.jpg")
    from playmemories_photo_manager.duplicates import detector

    original_open = detector._open_absolute_directory
    original_fstat = detector.os.fstat
    original_close = detector.os.close
    root_descriptors: set[int] = set()
    closed: set[int] = set()

    def tracking_open(path: str) -> int:
        descriptor = original_open(path)
        root_descriptors.add(descriptor)
        return descriptor

    def failing_fstat(descriptor: int):
        if descriptor in root_descriptors:
            raise OSError(errno.EIO, "injected fstat failure")
        return original_fstat(descriptor)

    def tracking_close(descriptor: int) -> None:
        if descriptor in root_descriptors:
            closed.add(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(detector, "_open_absolute_directory", tracking_open)
    monkeypatch.setattr(detector.os, "fstat", failing_fstat)
    monkeypatch.setattr(detector.os, "close", tracking_close)

    result = find_exact_duplicates(database)

    assert result.issues[0].kind is DuplicateIssueKind.INVALID_PATH
    assert closed == root_descriptors


def test_root_descriptor_is_closed_when_snapshot_creation_fails(
    database, tmp_path: Path, monkeypatch
) -> None:
    root_id = _root(database, tmp_path)
    _location(database, _asset(database), root_id, "one.jpg")
    from playmemories_photo_manager.duplicates import detector

    original_open = detector._open_absolute_directory
    original_snapshot = detector._snapshot
    original_close = detector.os.close
    root_descriptors: set[int] = set()
    closed: set[int] = set()

    def tracking_open(path: str) -> int:
        descriptor = original_open(path)
        root_descriptors.add(descriptor)
        return descriptor

    def failing_snapshot(info: os.stat_result):
        if info.st_mode & 0o170000 == 0o040000:
            raise RuntimeError("injected snapshot failure")
        return original_snapshot(info)

    def tracking_close(descriptor: int) -> None:
        if descriptor in root_descriptors:
            closed.add(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(detector, "_open_absolute_directory", tracking_open)
    monkeypatch.setattr(detector, "_snapshot", failing_snapshot)
    monkeypatch.setattr(detector.os, "close", tracking_close)

    with pytest.raises(RuntimeError, match="injected snapshot failure"):
        find_exact_duplicates(database)

    assert closed == root_descriptors


def test_detection_does_not_persist_hashes(database, tmp_path: Path) -> None:
    root_id = _root(database, tmp_path)
    for name in ("one.jpg", "two.jpg"):
        path = _write(tmp_path, name, b"same")
        _location(database, _asset(database), root_id, name, path=path)

    find_exact_duplicates(database)

    count = database.execute("SELECT count(*) FROM asset WHERE sha256 IS NOT NULL").fetchone()[0]
    assert count == 0


def test_empty_catalog_has_complete_coverage(database) -> None:
    result = find_exact_duplicates(database)

    assert result.coverage is DuplicateCoverage.COMPLETE
    assert result.groups == ()
    assert result.issues == ()


def test_unsupported_platform_fails_closed(database, tmp_path: Path, monkeypatch) -> None:
    root_id = _root(database, tmp_path)
    path = _write(tmp_path, "one.jpg", b"bytes")
    _location(database, _asset(database), root_id, "one.jpg", path=path)
    from playmemories_photo_manager.duplicates import detector

    monkeypatch.setattr(detector, "_confined_reads_supported", lambda: False)

    result = find_exact_duplicates(database)

    assert result.coverage is DuplicateCoverage.UNAVAILABLE
    assert result.issues[0].kind is DuplicateIssueKind.CONFINEMENT_UNAVAILABLE
