from __future__ import annotations

import os
import sqlite3
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from playmemories_photo_manager.catalog import initialize_database
from playmemories_photo_manager.scanner import (
    EntryType,
    EvidenceKind,
    FailureKind,
    ScanOptions,
    ScanStatus,
    scan,
)
from playmemories_photo_manager.scanner import service as scanner_service


def _write(path: Path, content: bytes = b"synthetic-photo") -> None:
    path.write_bytes(content)


def test_empty_root_is_complete(tmp_path: Path) -> None:
    result = scan(tmp_path)

    assert result.status is ScanStatus.COMPLETE
    assert result.is_complete is True
    assert result.entries == ()
    assert result.failures == ()
    assert result.covered_directories == (".",)
    assert result.root is not None
    assert result.scope.relative_path == "."
    assert result.scope.follows_links is False
    assert result.started_at <= result.finished_at


def test_files_subdirectories_unicode_and_deterministic_order(tmp_path: Path) -> None:
    (tmp_path / "b-dir").mkdir()
    _write(tmp_path / "b-dir" / "z.jpg", b"z")
    _write(tmp_path / "a.jpg", b"a")
    _write(tmp_path / "café.jpg", b"unicode")

    first = scan(tmp_path)
    second = scan(tmp_path)

    expected = ["a.jpg", "b-dir", "b-dir/z.jpg", "café.jpg"]
    assert [entry.relative_path for entry in first.entries] == expected
    assert [entry.relative_path for entry in second.entries] == expected
    assert [entry.entry_type for entry in first.entries] == [
        EntryType.FILE,
        EntryType.DIRECTORY,
        EntryType.FILE,
        EntryType.FILE,
    ]
    assert all(entry.evidence_kind is EvidenceKind.DIRECT_OBSERVATION for entry in first.entries)
    assert first.entries[0].byte_size == 1


def test_non_recursive_scope_observes_directory_but_not_children(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    _write(tmp_path / "nested" / "hidden.jpg")

    result = scan(tmp_path, ScanOptions(recursive=False))

    assert result.status is ScanStatus.COMPLETE
    assert result.scope.recursive is False
    assert [entry.relative_path for entry in result.entries] == ["nested"]


def test_different_names_and_exact_copies_remain_separate_observations(tmp_path: Path) -> None:
    _write(tmp_path / "first.jpg", b"same bytes")
    _write(tmp_path / "second.jpg", b"same bytes")

    result = scan(tmp_path)

    assert [entry.relative_path for entry in result.entries] == ["first.jpg", "second.jpg"]
    assert result.entries[0].byte_size == result.entries[1].byte_size
    assert not hasattr(result.entries[0], "sha256")


def test_hardlinks_have_separate_paths_and_observed_physical_identity(tmp_path: Path) -> None:
    original = tmp_path / "original.jpg"
    linked = tmp_path / "linked.jpg"
    _write(original)
    try:
        os.link(original, linked)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"hardlinks unavailable: {error}")

    result = scan(tmp_path)
    by_path = {entry.relative_path: entry for entry in result.entries}

    assert by_path["original.jpg"].physical_identity is not None
    assert by_path["linked.jpg"].physical_identity == by_path["original.jpg"].physical_identity
    assert len(result.entries) == 2


def test_physical_identity_can_be_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path / "photo.jpg")
    monkeypatch.setattr(scanner_service, "_physical_identity", lambda _observed: None)

    result = scan(tmp_path)

    assert result.root is not None and result.root.physical_identity is None
    assert result.entries[0].physical_identity is None


def test_symlinks_are_observed_and_never_followed(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    _write(outside / "outside.jpg")
    (tmp_path / "directory").mkdir()
    _write(tmp_path / "directory" / "inside.jpg")
    try:
        (tmp_path / "internal-link").symlink_to(tmp_path / "directory", target_is_directory=True)
        (tmp_path / "external-link").symlink_to(outside, target_is_directory=True)
        (tmp_path / "cycle").symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlinks unavailable: {error}")

    result = scan(tmp_path)
    by_path = {entry.relative_path: entry.entry_type for entry in result.entries}

    assert by_path["cycle"] is EntryType.SYMLINK
    assert by_path["external-link"] is EntryType.SYMLINK
    assert by_path["internal-link"] is EntryType.SYMLINK
    assert "directory/inside.jpg" in by_path
    assert all("outside.jpg" not in path for path in by_path)


def test_symlink_cannot_be_used_as_scan_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    link = tmp_path / "root-link"
    try:
        link.symlink_to(real_root, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlinks unavailable: {error}")

    result = scan(link)

    assert result.status is ScanStatus.ROOT_UNAVAILABLE
    assert result.failures[0].kind is FailureKind.SYMLINK_ROOT
    assert result.entries == ()


@pytest.mark.skipif(os.name == "nt", reason="descriptor-relative confinement is POSIX-only")
def test_directory_replaced_by_external_symlink_is_not_traversed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = tmp_path / "child"
    child.mkdir()
    _write(child / "inside.jpg")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-swap"
    outside.mkdir()
    _write(outside / "outside.jpg")
    original_open = scanner_service._open_directory
    swapped = False

    def swap_then_open(path: str | os.PathLike[str], *, dir_fd: int | None = None) -> int:
        nonlocal swapped
        if os.fspath(path) == "child" and dir_fd is not None and not swapped:
            swapped = True
            child.rename(tmp_path / "original-child")
            child.symlink_to(outside, target_is_directory=True)
        return original_open(path, dir_fd=dir_fd)

    monkeypatch.setattr(scanner_service, "_open_directory", swap_then_open)
    result = scan(tmp_path)

    assert result.status is ScanStatus.PARTIAL
    assert "child/outside.jpg" not in {entry.relative_path for entry in result.entries}
    assert any(failure.relative_path == "child" for failure in result.failures)


@pytest.mark.skipif(os.name == "nt", reason="descriptor-relative confinement is POSIX-only")
def test_root_replaced_by_symlink_after_lstat_is_not_traversed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside / "outside.jpg")
    original_lstat = scanner_service.os.lstat
    swapped = False

    def stat_then_swap(path: str | os.PathLike[str]) -> os.stat_result:
        nonlocal swapped
        observed = original_lstat(path)
        if Path(path) == root and not swapped:
            swapped = True
            root.rename(tmp_path / "original-root")
            root.symlink_to(outside, target_is_directory=True)
        return observed

    monkeypatch.setattr(scanner_service.os, "lstat", stat_then_swap)
    result = scan(root)

    assert result.status is ScanStatus.ROOT_UNAVAILABLE
    assert result.entries == ()
    assert result.failures


@pytest.mark.skipif(os.name == "nt", reason="descriptor-relative confinement is POSIX-only")
def test_root_path_change_during_enumeration_prevents_complete_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "photo.jpg")
    original_stat = scanner_service._stat_entry
    changed = False

    def stat_then_replace_root(entry: os.DirEntry[str]) -> os.stat_result:
        nonlocal changed
        observed = original_stat(entry)
        if not changed:
            changed = True
            root.rename(tmp_path / "original-root")
            root.mkdir()
        return observed

    monkeypatch.setattr(scanner_service, "_stat_entry", stat_then_replace_root)
    result = scan(root)

    assert result.status is ScanStatus.PARTIAL
    assert [entry.relative_path for entry in result.entries] == ["photo.jpg"]
    assert any(failure.relative_path is None for failure in result.failures)


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_unavailable_or_invalid_root_is_structured(tmp_path: Path, kind: str) -> None:
    root = tmp_path / kind
    if kind == "file":
        _write(root)

    result = scan(root)

    assert result.status is ScanStatus.ROOT_UNAVAILABLE
    assert result.entries == ()
    assert len(result.failures) == 1
    assert result.failures[0].compromises_coverage is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are required")
def test_inaccessible_root_is_not_reported_as_empty(tmp_path: Path) -> None:
    root = tmp_path / "denied"
    root.mkdir()
    root.chmod(0)
    try:
        result = scan(root)
        if result.status is ScanStatus.COMPLETE:
            pytest.skip("test process can bypass directory permission bits")
        assert result.status is ScanStatus.ROOT_UNAVAILABLE
        assert result.failures[0].kind is FailureKind.PERMISSION_DENIED
    finally:
        root.chmod(0o700)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are required")
def test_partial_enumeration_preserves_valid_observations(tmp_path: Path) -> None:
    _write(tmp_path / "visible.jpg")
    denied = tmp_path / "denied"
    denied.mkdir()
    _write(denied / "hidden.jpg")
    denied.chmod(0)
    try:
        result = scan(tmp_path)
        if result.status is ScanStatus.COMPLETE:
            pytest.skip("test process can bypass directory permission bits")
        assert result.status is ScanStatus.PARTIAL
        assert "visible.jpg" in {entry.relative_path for entry in result.entries}
        assert result.covered_directories == (".",)
        assert any(failure.kind is FailureKind.PERMISSION_DENIED for failure in result.failures)
    finally:
        denied.chmod(0o700)


def test_unclassified_root_enumeration_error_is_total_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_enumeration(_path: Path) -> None:
        raise OSError("synthetic I/O failure")

    monkeypatch.setattr(scanner_service.os, "scandir", fail_enumeration)

    result = scan(tmp_path)

    assert result.status is ScanStatus.FAILED
    assert result.entries == ()
    assert result.failures[0].kind is FailureKind.IO_ERROR


def test_disappearing_entry_is_a_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vanishing = tmp_path / "vanishing.jpg"
    stable = tmp_path / "stable.jpg"
    _write(stable)
    _write(vanishing)
    original_stat = scanner_service._stat_entry

    def remove_then_stat(entry: os.DirEntry[str]) -> os.stat_result:
        if entry.name == vanishing.name:
            vanishing.unlink(missing_ok=True)
        return original_stat(entry)

    monkeypatch.setattr(scanner_service, "_stat_entry", remove_then_stat)
    result = scan(tmp_path)

    assert result.status is ScanStatus.PARTIAL
    assert [entry.relative_path for entry in result.entries] == ["stable.jpg"]
    assert result.failures[0].kind is FailureKind.DISAPPEARED
    assert result.failures[0].relative_path == "vanishing.jpg"


def test_cancellation_preserves_observations_without_claiming_completion(tmp_path: Path) -> None:
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        _write(tmp_path / name)
    checks = 0

    def cancellation_requested() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    result = scan(tmp_path, ScanOptions(cancellation_requested=cancellation_requested))

    assert result.status is ScanStatus.CANCELLED
    assert [entry.relative_path for entry in result.entries] == ["a.jpg"]
    assert result.is_complete is False


def test_cancellation_after_empty_directory_collection_is_honored(tmp_path: Path) -> None:
    checks = 0

    def cancellation_requested() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    result = scan(tmp_path, ScanOptions(cancellation_requested=cancellation_requested))

    assert result.status is ScanStatus.CANCELLED
    assert result.covered_directories == (".",)
    assert result.entries == ()


def test_scan_does_not_change_contents_or_create_files(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    photo = nested / "photo.jpg"
    content = b"synthetic immutable content"
    _write(photo, content)
    before_names = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    before_mode = photo.stat().st_mode
    before_mtime = photo.stat().st_mtime_ns

    result = scan(tmp_path)

    after_names = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert result.status is ScanStatus.COMPLETE
    assert photo.read_bytes() == content
    assert photo.stat().st_mode == before_mode
    assert photo.stat().st_mtime_ns == before_mtime
    assert after_names == before_names
    assert not any(path.suffix.lower() in {".xmp", ".json"} for path in tmp_path.rglob("*"))


def test_scan_has_no_database_side_effect(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"
    connection = initialize_database(database_path)
    before = connection.execute(
        "SELECT (SELECT count(*) FROM asset), (SELECT count(*) FROM file_location)"
    ).fetchone()
    root = tmp_path / "media"
    root.mkdir()
    _write(root / "photo.jpg")

    result = scan(root)

    after = connection.execute(
        "SELECT (SELECT count(*) FROM asset), (SELECT count(*) FROM file_location)"
    ).fetchone()
    connection.close()
    assert result.status is ScanStatus.COMPLETE
    assert tuple(before) == tuple(after) == (0, 0)


def test_results_are_immutable_and_options_are_validated(tmp_path: Path) -> None:
    result = scan(tmp_path)
    with pytest.raises(FrozenInstanceError):
        result.status = ScanStatus.PARTIAL  # type: ignore[misc]
    with pytest.raises(TypeError, match="ScanOptions"):
        scan(tmp_path, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="recursive"):
        ScanOptions(recursive=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="cancellation_requested"):
        ScanOptions(cancellation_requested=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="root_path"):
        scan("")


def test_database_module_is_not_a_scanner_dependency() -> None:
    assert "sqlite3" not in scanner_service.__dict__
    assert "Catalog" not in scanner_service.__dict__
    assert sqlite3.Connection is not None
