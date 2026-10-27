"""POSIX-confined, read-only detection of catalogued exact duplicates."""

from __future__ import annotations

import errno
import hashlib
import os
import sqlite3
import stat
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath

from .models import (
    DuplicateCoverage,
    DuplicateIssue,
    DuplicateIssueKind,
    DuplicateMember,
    ExactDuplicateGroup,
    ExactDuplicateResult,
)

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class _CatalogLocation:
    asset_id: str
    asset_sha256: str | None
    hash_state: str
    location_id: str
    root_id: str
    root_path: str
    root_availability: str
    relative_path: str
    entry_type: str
    availability: str
    observed_size: int | None
    observed_mtime_ns: int | None
    filesystem_id: str | None


@dataclass(frozen=True, slots=True)
class _Snapshot:
    mode: int
    device: int
    file_id: int
    size: int
    mtime_ns: int
    ctime_ns: int
    link_count: int


@dataclass(frozen=True, slots=True)
class _Candidate:
    catalog: _CatalogLocation
    snapshot: _Snapshot


def find_exact_duplicates(connection: sqlite3.Connection) -> ExactDuplicateResult:
    """Hash eligible catalog locations without mutating the catalog or media tree."""
    rows = _catalog_locations(connection)
    eligible_count = sum(
        row.root_availability == "available"
        and row.availability == "present"
        and row.entry_type == "file"
        for row in rows
    )
    if not _confined_reads_supported():
        issues = tuple(
            _issue(DuplicateIssueKind.CONFINEMENT_UNAVAILABLE, row)
            for row in rows
            if row.root_availability == "available"
            and row.availability == "present"
            and row.entry_type == "file"
        )
        return ExactDuplicateResult(DuplicateCoverage.UNAVAILABLE, (), issues, eligible_count, 0)

    issues: list[DuplicateIssue] = []
    candidates: list[_Candidate] = []
    by_root: dict[tuple[str, str], list[_CatalogLocation]] = defaultdict(list)
    for row in rows:
        if row.root_availability != "available":
            issues.append(_issue(DuplicateIssueKind.ROOT_OFFLINE, row))
        elif row.availability != "present":
            issues.append(_issue(DuplicateIssueKind.LOCATION_UNAVAILABLE, row))
        elif row.entry_type != "file":
            issues.append(_issue(DuplicateIssueKind.SYMLINK_BLOCKED, row))
        else:
            by_root[(row.root_id, row.root_path)].append(row)

    root_descriptors: dict[str, tuple[int, _Snapshot]] = {}
    try:
        for (root_id, root_path), locations in sorted(by_root.items()):
            try:
                root_fd = _open_absolute_directory(root_path)
                root_snapshot = _snapshot(os.fstat(root_fd))
                root_descriptors[root_id] = (root_fd, root_snapshot)
            except (OSError, ValueError):
                issues.extend(_issue(DuplicateIssueKind.INVALID_PATH, row) for row in locations)
                continue
            for row in locations:
                try:
                    snapshot = _observe_regular(root_fd, row.relative_path)
                except ValueError:
                    issues.append(_issue(DuplicateIssueKind.INVALID_PATH, row))
                except OSError as error:
                    if error.errno == errno.ELOOP:
                        kind = DuplicateIssueKind.SYMLINK_BLOCKED
                    elif error.errno == errno.EINVAL:
                        kind = DuplicateIssueKind.NOT_REGULAR_FILE
                    else:
                        kind = DuplicateIssueKind.READ_FAILED
                    issues.append(_issue(kind, row))
                else:
                    if not _matches_catalog(snapshot, row):
                        issues.append(_issue(DuplicateIssueKind.FILE_CHANGED, row))
                    else:
                        candidates.append(_Candidate(row, snapshot))

        size_groups: dict[int, list[_Candidate]] = defaultdict(list)
        for candidate in candidates:
            size_groups[candidate.snapshot.size].append(candidate)

        hashed: list[DuplicateMember] = []
        for size in sorted(size_groups):
            same_size = size_groups[size]
            if len(same_size) < 2:
                continue
            for candidate in same_size:
                root_fd = root_descriptors[candidate.catalog.root_id][0]
                try:
                    digest = _checked_hash(root_fd, candidate)
                except ValueError:
                    issues.append(_issue(DuplicateIssueKind.INVALID_PATH, candidate.catalog))
                    continue
                except OSError as error:
                    kind = (
                        DuplicateIssueKind.SYMLINK_BLOCKED
                        if error.errno == errno.ELOOP
                        else DuplicateIssueKind.FILE_CHANGED
                    )
                    issues.append(_issue(kind, candidate.catalog))
                    continue
                if (
                    candidate.catalog.hash_state == "verified"
                    and candidate.catalog.asset_sha256 != digest
                ):
                    issues.append(_issue(DuplicateIssueKind.FILE_CHANGED, candidate.catalog))
                    continue
                snapshot = candidate.snapshot
                hashed.append(
                    DuplicateMember(
                        asset_id=candidate.catalog.asset_id,
                        location_id=candidate.catalog.location_id,
                        library_root_id=candidate.catalog.root_id,
                        relative_path=candidate.catalog.relative_path,
                        byte_size=snapshot.size,
                        sha256=digest,
                        device=snapshot.device,
                        file_id=snapshot.file_id,
                        link_count=snapshot.link_count,
                    )
                )

        invalid_roots = set()
        for root_id, (_root_fd, expected) in root_descriptors.items():
            root_path = next(path for key, path in by_root if key == root_id)
            try:
                check_fd = _open_absolute_directory(root_path)
                try:
                    current = _snapshot(os.fstat(check_fd))
                finally:
                    os.close(check_fd)
            except (OSError, ValueError):
                invalid_roots.add(root_id)
            else:
                if current != expected:
                    invalid_roots.add(root_id)
        if invalid_roots:
            retained = []
            invalid_locations = {
                member.location_id for member in hashed if member.library_root_id in invalid_roots
            }
            for candidate in candidates:
                if candidate.catalog.root_id in invalid_roots:
                    issues.append(_issue(DuplicateIssueKind.FILE_CHANGED, candidate.catalog))
            retained.extend(
                member for member in hashed if member.location_id not in invalid_locations
            )
            hashed = retained
    finally:
        for root_fd, _snapshot_value in root_descriptors.values():
            os.close(root_fd)

    digest_groups: dict[tuple[str, int], list[DuplicateMember]] = defaultdict(list)
    for member in hashed:
        digest_groups[(member.sha256, member.byte_size)].append(member)
    groups = []
    for (digest, size), members in sorted(digest_groups.items()):
        if len(members) < 2:
            continue
        ordered = tuple(
            sorted(
                members,
                key=lambda item: (
                    item.library_root_id,
                    item.relative_path,
                    item.location_id,
                    item.asset_id,
                ),
            )
        )
        groups.append(
            ExactDuplicateGroup(
                sha256=digest,
                byte_size=size,
                members=ordered,
                physical_copy_count=len({member.physical_identity for member in ordered}),
            )
        )
    ordered_issues = tuple(
        sorted(
            set(issues),
            key=lambda item: (
                item.library_root_id,
                item.relative_path,
                item.location_id,
                item.kind,
            ),
        )
    )
    coverage = DuplicateCoverage.COMPLETE if not ordered_issues else DuplicateCoverage.PARTIAL
    return ExactDuplicateResult(
        coverage, tuple(groups), ordered_issues, eligible_count, len(hashed)
    )


def _catalog_locations(connection: sqlite3.Connection) -> tuple[_CatalogLocation, ...]:
    with _read_snapshot(connection):
        rows = connection.execute(
            """SELECT a.id AS asset_id, a.sha256 AS asset_sha256, a.hash_state,
                fl.id AS location_id, fl.library_root_id AS root_id,
                lr.normalized_path AS root_path, lr.availability AS root_availability,
                fl.normalized_relative_path AS relative_path, fl.entry_type, fl.availability,
                fl.observed_byte_size AS observed_size, fl.observed_mtime_ns, fl.filesystem_id
            FROM file_location AS fl
            JOIN asset AS a ON a.id = fl.asset_id
            JOIN library_root AS lr ON lr.id = fl.library_root_id
            ORDER BY lr.id, fl.normalized_relative_path, fl.id, a.id"""
        ).fetchall()
    return tuple(_CatalogLocation(**dict(row)) for row in rows)


@contextmanager
def _read_snapshot(connection: sqlite3.Connection):
    name = "exact_duplicate_read_snapshot"
    connection.execute(f"SAVEPOINT {name}")
    try:
        yield
    finally:
        connection.execute(f"RELEASE SAVEPOINT {name}")


def _confined_reads_supported() -> bool:
    return (
        os.name == "posix"
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
    )


def _open_absolute_directory(path: str) -> int:
    pure = PurePosixPath(path)
    if not pure.is_absolute() or pure.as_posix() != path or ".." in pure.parts:
        raise ValueError("root path must be a canonical absolute POSIX path")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in pure.parts[1:]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _relative_parts(relative_path: str) -> tuple[str, ...]:
    pure = PurePosixPath(relative_path)
    if (
        not relative_path
        or pure.is_absolute()
        or pure.as_posix() != relative_path
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError("location path must be canonical and relative")
    return pure.parts


@contextmanager
def _open_regular(root_fd: int, relative_path: str):
    parts = _relative_parts(relative_path)
    directory_fd = os.dup(root_fd)
    file_fd = None
    try:
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        file_fd = os.open(parts[-1], flags, dir_fd=directory_fd)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(errno.EINVAL, "location is not a regular file")
        yield file_fd, directory_fd, parts[-1], _snapshot(info)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)


def _observe_regular(root_fd: int, relative_path: str) -> _Snapshot:
    with _open_regular(root_fd, relative_path) as (_fd, _parent, _name, snapshot):
        return snapshot


def _checked_hash(root_fd: int, candidate: _Candidate) -> str:
    with _open_regular(root_fd, candidate.catalog.relative_path) as (
        file_fd,
        parent_fd,
        name,
        before,
    ):
        if before != candidate.snapshot:
            raise OSError(errno.ESTALE, "file changed before hashing")
        digest = hashlib.sha256()
        while chunk := os.read(file_fd, _CHUNK_SIZE):
            digest.update(chunk)
        after = _snapshot(os.fstat(file_fd))
        path_after = _snapshot(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        if after != before or path_after != after:
            raise OSError(errno.ESTALE, "file changed during hashing")
        return digest.hexdigest()


def _snapshot(info: os.stat_result) -> _Snapshot:
    return _Snapshot(
        mode=stat.S_IFMT(info.st_mode),
        device=info.st_dev,
        file_id=info.st_ino,
        size=info.st_size,
        mtime_ns=info.st_mtime_ns,
        ctime_ns=info.st_ctime_ns,
        link_count=info.st_nlink,
    )


def _matches_catalog(snapshot: _Snapshot, row: _CatalogLocation) -> bool:
    if row.observed_size is not None and row.observed_size != snapshot.size:
        return False
    if row.observed_mtime_ns is not None and row.observed_mtime_ns != snapshot.mtime_ns:
        return False
    if row.filesystem_id is not None:
        return row.filesystem_id == f"scanner:{snapshot.device}:{snapshot.file_id}"
    return True


def _issue(kind: DuplicateIssueKind, row: _CatalogLocation) -> DuplicateIssue:
    return DuplicateIssue(
        kind=kind,
        asset_id=row.asset_id,
        location_id=row.location_id,
        library_root_id=row.root_id,
        relative_path=row.relative_path,
    )
