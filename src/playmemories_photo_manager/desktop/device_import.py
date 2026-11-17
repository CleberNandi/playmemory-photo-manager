"""Safe confined copy of eligible media from connected devices or source folders."""

from __future__ import annotations

import hashlib
import os
import stat
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from ..catalog_ingestion.capture import extract_capture
from ..catalog_ingestion.images import EXTENSIONS, MAX_BYTES
from ..catalog_ingestion.media import _Directories
from ..catalog_ingestion.root_grants import _HeldRoot
from ..library import LibraryError, LibrarySession
from .devices import resolve_device_mount_path

_MAX_DEPTH = 32
_MAX_ENTRIES = 2000
_MAX_FDS = 240
_CHUNK_BYTES = 65536


def _valid_path_arg(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 4096 or "\0" in value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        return None
    return value


def _sha256_fd(fd: int) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while chunk := os.read(fd, _CHUNK_BYTES):
        digest.update(chunk)
    return digest.hexdigest()


def _is_protected(candidate: Path, protected: tuple[Path, ...]) -> bool:
    for item in protected:
        try:
            resolved = item.resolve(strict=False)
        except OSError:
            continue
        if candidate == resolved or candidate.is_relative_to(resolved):
            return True
    return False


def _ensure_dest_dir(
    dest_root: _HeldRoot,
    dest_dirs: _Directories,
    rel_parent: PurePosixPath,
) -> int:
    current = dest_root.fd
    for part in rel_parent.parts:
        with suppress(FileExistsError):
            os.mkdir(part, 0o755, dir_fd=current)
        current = dest_dirs.child(current, part, dest_root.mount)
    return current


def _choose_target_name(
    dest_dir_fd: int,
    original_name: str,
    source_size: int,
    source_sha256: str,
) -> str | None:
    """Return a non-colliding filename, or None if an identical file already exists."""
    candidate = original_name
    stem = Path(original_name).stem
    suffix = Path(original_name).suffix
    for attempt in range(0, 10000):
        if attempt > 0:
            candidate = f"{stem} ({attempt}){suffix}"
        try:
            info = os.stat(candidate, dir_fd=dest_dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            return candidate
        if attempt == 0 and stat.S_ISREG(info.st_mode) and info.st_size == source_size:
            existing_fd = os.open(
                candidate,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=dest_dir_fd,
            )
            try:
                if _sha256_fd(existing_fd) == source_sha256:
                    return None
            finally:
                os.close(existing_fd)
    raise LibraryError("resource_limit")


def _date_folder_for_file(file_fd: int, mtime_ns: int) -> PurePosixPath:
    os.lseek(file_fd, 0, os.SEEK_SET)
    with os.fdopen(os.dup(file_fd), "rb", closefd=True) as stream:
        observations = extract_capture(stream)
    for priority in ("DateTimeOriginal", "DateTimeDigitized"):
        for name, _raw, local, *_ in observations:
            if name == priority and isinstance(local, str) and len(local) >= 7:
                return PurePosixPath(local[:4]) / local[5:7]
    dt = datetime.fromtimestamp(mtime_ns // 1_000_000_000, tz=UTC).astimezone()
    return PurePosixPath(f"{dt.year:04d}") / f"{dt.month:02d}"


def _copy_file_atomic(
    source_fd: int,
    source_info: os.stat_result,
    dest_dir_fd: int,
    target_name: str,
) -> None:
    tmp_name = f".pm-import-{uuid4().hex}.tmp"
    os.lseek(source_fd, 0, os.SEEK_SET)
    out_fd = os.open(
        tmp_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o644,
        dir_fd=dest_dir_fd,
    )
    linked = False
    try:
        while chunk := os.read(source_fd, _CHUNK_BYTES):
            written = 0
            while written < len(chunk):
                written += os.write(out_fd, chunk[written:])
        os.fsync(out_fd)
        with suppress(OSError):
            os.utime(out_fd, ns=(source_info.st_atime_ns, source_info.st_mtime_ns))
        os.close(out_fd)
        out_fd = -1
        os.link(tmp_name, target_name, src_dir_fd=dest_dir_fd, dst_dir_fd=dest_dir_fd)
        linked = True
    finally:
        if out_fd >= 0:
            with suppress(OSError):
                os.close(out_fd)
        if not linked:
            with suppress(OSError):
                os.unlink(tmp_name, dir_fd=dest_dir_fd)
    with suppress(OSError):
        os.unlink(tmp_name, dir_fd=dest_dir_fd)


def import_from_media(
    active: LibrarySession,
    *,
    device_id: object = None,
    source_path: object = None,
    destination_path: object = None,
    organize_by_date: object = False,
    protected_paths: tuple[Path, ...] = (),
) -> dict:
    """Copy eligible media from a mounted device or folder into destination_path."""
    if type(organize_by_date) is not bool:
        raise LibraryError("invalid_request")
    dest_str = _valid_path_arg(destination_path)
    if dest_str is None:
        raise LibraryError("invalid_request")

    resolved_source: Path | None = None
    if source_path is not None:
        src_str = _valid_path_arg(source_path)
        if src_str is None:
            raise LibraryError("invalid_request")
        resolved_source = Path(src_str)
    elif isinstance(device_id, str) and device_id:
        resolved_source = resolve_device_mount_path(device_id)
        if resolved_source is None:
            return {"status": "source_not_mounted"}
    else:
        raise LibraryError("invalid_request")

    catalog_dir = active.catalog_binding[0].parent
    dest_candidate = Path(dest_str)
    try:
        dest_real = dest_candidate.resolve(strict=True)
        src_real = resolved_source.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise LibraryError("unsafe_location") from error

    if _is_protected(dest_real, (catalog_dir, *protected_paths)):
        raise LibraryError("unsafe_location")
    if (
        src_real == dest_real
        or dest_real.is_relative_to(src_real)
        or src_real.is_relative_to(dest_real)
    ):
        raise LibraryError("unsafe_location")

    try:
        source_root = _HeldRoot(src_real)
    except OSError as error:
        raise LibraryError("unsafe_location") from error
    try:
        dest_root = _HeldRoot(dest_real)
    except OSError as error:
        source_root.close()
        raise LibraryError("unsafe_location") from error

    source_dirs = _Directories()
    dest_dirs = _Directories()
    copied_count = 0
    skipped_count = 0
    excluded_count = 0
    seen_entries = 0

    try:

        def walk(src_fd: int, rel_dir: PurePosixPath, depth: int) -> None:
            nonlocal copied_count, skipped_count, excluded_count, seen_entries
            if depth > _MAX_DEPTH or len(source_dirs.fds) > _MAX_FDS:
                raise LibraryError("resource_limit")
            with os.scandir(src_fd) as entries:
                children: list[tuple[str, os.stat_result]] = []
                for item in entries:
                    seen_entries += 1
                    if seen_entries > _MAX_ENTRIES:
                        raise LibraryError("resource_limit")
                    children.append((item.name, item.stat(follow_symlinks=False)))
            for name, info in sorted(children):
                if stat.S_ISLNK(info.st_mode):
                    excluded_count += 1
                    continue
                if stat.S_ISDIR(info.st_mode):
                    child_fd = source_dirs.child(src_fd, name, source_root.mount)
                    walk(child_fd, rel_dir / name, depth + 1)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    excluded_count += 1
                    continue
                if Path(name).suffix.lower() not in EXTENSIONS:
                    excluded_count += 1
                    continue
                if info.st_size <= 0 or info.st_size > MAX_BYTES:
                    excluded_count += 1
                    continue
                file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=src_fd)
                try:
                    actual_info = os.fstat(file_fd)
                    if (
                        not stat.S_ISREG(actual_info.st_mode)
                        or actual_info.st_size <= 0
                        or actual_info.st_size > MAX_BYTES
                    ):
                        excluded_count += 1
                        continue
                    digest = _sha256_fd(file_fd)
                    target_rel_dir = (
                        _date_folder_for_file(file_fd, actual_info.st_mtime_ns)
                        if organize_by_date
                        else rel_dir
                    )
                    dest_dir_fd = _ensure_dest_dir(dest_root, dest_dirs, target_rel_dir)
                    target_name = _choose_target_name(
                        dest_dir_fd,
                        name,
                        actual_info.st_size,
                        digest,
                    )
                    if target_name is None:
                        skipped_count += 1
                        continue
                    _copy_file_atomic(file_fd, actual_info, dest_dir_fd, target_name)
                    copied_count += 1
                finally:
                    os.close(file_fd)

        walk(source_root.fd, PurePosixPath(), 0)
        source_dirs.check()
        dest_dirs.check()
        source_root.check()
        dest_root.check()
    finally:
        source_dirs.close()
        dest_dirs.close()
        source_root.close()
        dest_root.close()

    return {
        "status": "ready",
        "copied_count": copied_count,
        "skipped_count": skipped_count,
        "excluded_count": excluded_count,
        "destination_path": str(dest_real),
    }
