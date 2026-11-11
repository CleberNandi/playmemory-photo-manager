"""Resolve a catalog occurrence for explicit trusted-shell reveal, never the renderer."""

import os
import stat
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from ..catalog_ingestion.media import _Changed, _Directories, _mount_id
from ..library import LibraryError


@contextmanager
def held_location(connection, asset_id, *, location_id=None):
    row = connection.execute(
        """SELECT fl.*,lr.normalized_path FROM file_location fl
        JOIN library_root lr ON lr.id=fl.library_root_id
        WHERE fl.asset_id=? AND fl.entry_type='file' AND fl.availability='present'
        AND lr.availability='available' AND (? IS NULL OR fl.id=?)
        ORDER BY fl.id LIMIT 1""",
        (asset_id, location_id, location_id),
    ).fetchone()
    if row is None or not row["filesystem_id"]:
        raise LibraryError("not_found")
    root = Path(row["normalized_path"])
    relative = PurePosixPath(row["normalized_relative_path"])
    if (
        not root.is_absolute()
        or str(root) != row["normalized_path"]
        or ".." in root.parts
        or relative.is_absolute()
        or str(relative) != row["normalized_relative_path"]
        or ".." in relative.parts
        or not relative.parts
        or len(root.parts) + len(relative.parts) > 64
        or "\0" in str(root / relative)
    ):
        raise LibraryError("unsafe_location")
    directories = _Directories()
    fd = None
    try:
        parent = directories.start()
        for component in root.parts[1:]:
            parent = directories.child(parent, component)
        mount = _mount_id(parent)
        for component in relative.parts[:-1]:
            parent = directories.child(parent, component, mount)
        fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or _mount_id(fd) != mount
            or row["filesystem_id"] != f"scanner:{info.st_dev}:{info.st_ino}"
            or info.st_size != row["observed_byte_size"]
            or info.st_mtime_ns != row["observed_mtime_ns"]
        ):
            raise LibraryError("unsafe_location")
        directories.check()
        yield row, directories, parent, fd, info, root / relative
    except LibraryError:
        raise
    except (OSError, RuntimeError, _Changed):
        raise LibraryError("unsafe_location") from None
    finally:
        if fd is not None:
            os.close(fd)
        directories.close()


def reveal_location(connection, asset_id):
    with held_location(connection, asset_id) as (_, _, _, _, _, path):
        return {"path": str(path)}
