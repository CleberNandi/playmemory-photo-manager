"""Sequential, read-only filesystem observation."""

from __future__ import annotations

import os
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .models import (
    EntryObservation,
    EntryType,
    FailureKind,
    FailureOperation,
    ObservationFailure,
    ObservedTimestamps,
    PhysicalIdentity,
    RootObservation,
    ScanOptions,
    ScanResult,
    ScanScope,
    ScanStatus,
)


def scan(root_path: str | os.PathLike[str], options: ScanOptions | None = None) -> ScanResult:
    """Observe one explicit root without following links or changing persistent state."""
    options = options or ScanOptions()
    if not isinstance(options, ScanOptions):
        raise TypeError("options must be ScanOptions or None")
    if not os.fspath(root_path):
        raise ValueError("root_path must not be empty")
    root = Path(root_path)
    absolute_root = Path(os.path.abspath(root))
    started_at = _now()
    run_id = str(uuid.uuid4())
    scope = ScanScope(relative_path=".", recursive=options.recursive, follows_links=False)
    entries: list[EntryObservation] = []
    failures: list[ObservationFailure] = []
    covered_directories: list[str] = []

    try:
        root_stat = os.lstat(absolute_root)
    except OSError as error:
        failures.append(_failure(None, FailureOperation.OBSERVE_ROOT, error))
        return _result(
            run_id,
            None,
            scope,
            started_at,
            ScanStatus.ROOT_UNAVAILABLE,
            covered_directories,
            entries,
            failures,
        )

    root_observation = RootObservation(
        requested_path=os.fspath(root),
        absolute_path=os.fspath(absolute_root),
        physical_identity=_physical_identity(root_stat),
    )
    if stat.S_ISLNK(root_stat.st_mode):
        failures.append(
            ObservationFailure(
                relative_path=None,
                operation=FailureOperation.OBSERVE_ROOT,
                kind=FailureKind.SYMLINK_ROOT,
                compromises_coverage=True,
                error_code=None,
            )
        )
        return _result(
            run_id,
            root_observation,
            scope,
            started_at,
            ScanStatus.ROOT_UNAVAILABLE,
            covered_directories,
            entries,
            failures,
        )
    if _is_reparse(root_stat) or _is_junction(absolute_root):
        failures.append(
            ObservationFailure(
                relative_path=None,
                operation=FailureOperation.OBSERVE_ROOT,
                kind=FailureKind.REPARSE_ROOT,
                compromises_coverage=True,
                error_code=None,
            )
        )
        return _result(
            run_id,
            root_observation,
            scope,
            started_at,
            ScanStatus.ROOT_UNAVAILABLE,
            covered_directories,
            entries,
            failures,
        )
    if not stat.S_ISDIR(root_stat.st_mode):
        failures.append(
            ObservationFailure(
                relative_path=None,
                operation=FailureOperation.OBSERVE_ROOT,
                kind=FailureKind.NOT_DIRECTORY,
                compromises_coverage=True,
                error_code=None,
            )
        )
        return _result(
            run_id,
            root_observation,
            scope,
            started_at,
            ScanStatus.ROOT_UNAVAILABLE,
            covered_directories,
            entries,
            failures,
        )

    cancelled, root_failed = _walk(
        absolute_root,
        PurePosixPath("."),
        options,
        covered_directories,
        entries,
        failures,
    )
    if cancelled:
        status = ScanStatus.CANCELLED
    elif root_failed:
        status = (
            ScanStatus.ROOT_UNAVAILABLE
            if failures[-1].kind in {FailureKind.PERMISSION_DENIED, FailureKind.DISAPPEARED}
            else ScanStatus.FAILED
        )
    elif failures:
        status = ScanStatus.PARTIAL
    else:
        status = ScanStatus.COMPLETE
    return _result(
        run_id,
        root_observation,
        scope,
        started_at,
        status,
        covered_directories,
        entries,
        failures,
    )


def _walk(
    directory: Path,
    relative_directory: PurePosixPath,
    options: ScanOptions,
    covered_directories: list[str],
    observations: list[EntryObservation],
    failures: list[ObservationFailure],
) -> tuple[bool, bool]:
    if _cancelled(options):
        return True, False
    try:
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda item: item.name)
    except OSError as error:
        failures.append(
            _failure(_display_path(relative_directory), FailureOperation.ENUMERATE_DIRECTORY, error)
        )
        return False, relative_directory == PurePosixPath(".")
    covered_directories.append(_display_path(relative_directory))

    for child in children:
        if _cancelled(options):
            return True, False
        relative_path = relative_directory / child.name
        try:
            observed_stat = _stat_entry(child)
            entry_type = _entry_type(child, observed_stat)
        except OSError as error:
            failures.append(
                _failure(_display_path(relative_path), FailureOperation.OBSERVE_ENTRY, error)
            )
            continue
        observations.append(_observation(relative_path, entry_type, observed_stat))
        if entry_type is EntryType.DIRECTORY and options.recursive:
            cancelled, _ = _walk(
                Path(child.path),
                relative_path,
                options,
                covered_directories,
                observations,
                failures,
            )
            if cancelled:
                return True, False
    return False, False


def _stat_entry(entry: os.DirEntry[str]) -> os.stat_result:
    return entry.stat(follow_symlinks=False)


def _entry_type(entry: os.DirEntry[str], observed_stat: os.stat_result) -> EntryType:
    if entry.is_symlink():
        return EntryType.SYMLINK
    is_junction = getattr(entry, "is_junction", None)
    if is_junction is not None and is_junction():
        return EntryType.REPARSE_POINT
    if _is_reparse(observed_stat):
        return EntryType.REPARSE_POINT
    if stat.S_ISDIR(observed_stat.st_mode):
        return EntryType.DIRECTORY
    if stat.S_ISREG(observed_stat.st_mode):
        return EntryType.FILE
    return EntryType.OTHER


def _observation(
    relative_path: PurePosixPath, entry_type: EntryType, observed_stat: os.stat_result
) -> EntryObservation:
    return EntryObservation(
        relative_path=_display_path(relative_path),
        entry_type=entry_type,
        byte_size=observed_stat.st_size if entry_type is EntryType.FILE else None,
        timestamps=ObservedTimestamps(
            modified_ns=getattr(observed_stat, "st_mtime_ns", None),
            accessed_ns=getattr(observed_stat, "st_atime_ns", None),
            changed_ns=getattr(observed_stat, "st_ctime_ns", None),
        ),
        physical_identity=_physical_identity(observed_stat),
    )


def _physical_identity(observed_stat: os.stat_result) -> PhysicalIdentity | None:
    device = getattr(observed_stat, "st_dev", None)
    file_id = getattr(observed_stat, "st_ino", None)
    if not isinstance(device, int) or not isinstance(file_id, int) or file_id == 0:
        return None
    return PhysicalIdentity(device=device, file_id=file_id)


def _is_reparse(observed_stat: os.stat_result) -> bool:
    attributes = getattr(observed_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _is_junction(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction is not None and is_junction(path))


def _failure(
    relative_path: str | None, operation: FailureOperation, error: OSError
) -> ObservationFailure:
    if isinstance(error, PermissionError):
        kind = FailureKind.PERMISSION_DENIED
    elif isinstance(error, FileNotFoundError):
        kind = FailureKind.DISAPPEARED
    else:
        kind = FailureKind.IO_ERROR
    return ObservationFailure(
        relative_path=relative_path,
        operation=operation,
        kind=kind,
        compromises_coverage=True,
        error_code=error.errno,
    )


def _cancelled(options: ScanOptions) -> bool:
    return options.cancellation_requested is not None and options.cancellation_requested()


def _display_path(path: PurePosixPath) -> str:
    return path.as_posix()


def _result(
    run_id: str,
    root: RootObservation | None,
    scope: ScanScope,
    started_at: datetime,
    status: ScanStatus,
    covered_directories: list[str],
    entries: list[EntryObservation],
    failures: list[ObservationFailure],
) -> ScanResult:
    return ScanResult(
        run_id=run_id,
        root=root,
        scope=scope,
        started_at=started_at,
        finished_at=_now(),
        status=status,
        covered_directories=tuple(covered_directories),
        entries=tuple(entries),
        failures=tuple(failures),
    )


def _now() -> datetime:
    return datetime.now(UTC)
