"""Validate a prospective in-place rename against the catalog and held source directory."""

import os
from pathlib import PurePosixPath

from ..library import LibraryError
from .media_location import held_location


def preview_rename(connection, asset_id: str, location_id: str, stem: object) -> dict:
    if (
        not isinstance(stem, str)
        or not stem
        or len(stem) > 255
        or stem.strip() != stem
        or stem in (".", "..")
        or any(char in "/\\" or not char.isprintable() for char in stem)
    ):
        return {"status": "invalid_name"}

    try:
        with held_location(connection, asset_id, location_id=location_id) as (
            row,
            directories,
            parent,
            _fd,
            observed,
            _path,
        ):
            current = PurePosixPath(row["normalized_relative_path"])
            name = stem + current.suffix
            max_bytes = os.fpathconf(parent, "PC_NAME_MAX")
            if len(os.fsencode(name)) > (max_bytes if max_bytes > 0 else 255):
                return {"status": "invalid_name"}
            if name == current.name:
                return {"status": "same_name"}
            proposed = current.with_name(name).as_posix()
            if connection.execute(
                """SELECT 1 FROM file_location
                WHERE library_root_id=? AND normalized_relative_path=?
                  AND availability<>'missing'""",
                (row["library_root_id"], proposed),
            ).fetchone():
                return {"status": "name_taken"}
            try:
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                return {"status": "name_taken"}
            directories.check()
            source = os.stat(current.name, dir_fd=parent, follow_symlinks=False)
            if (source.st_dev, source.st_ino, source.st_ctime_ns) != (
                observed.st_dev,
                observed.st_ino,
                observed.st_ctime_ns,
            ):
                return {"status": "source_unavailable"}
            return {
                "status": "ready",
                "current_relative_path": current.as_posix(),
                "proposed_relative_path": proposed,
            }
    except LibraryError:
        return {"status": "source_unavailable"}
    except ValueError:
        return {"status": "invalid_name"}
