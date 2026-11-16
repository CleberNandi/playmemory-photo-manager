"""Validate and apply an in-place rename against the catalog and held source directory."""

import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import PurePosixPath

from ..library import LibraryError
from .media_location import held_location


def _valid_stem(stem: object) -> bool:
    return (
        isinstance(stem, str)
        and bool(stem)
        and len(stem) <= 255
        and stem.strip() == stem
        and stem not in (".", "..")
        and not any(char in "/\\" or not char.isprintable() for char in stem)
    )


def _check_rename_target(connection, row, directories, parent, observed, stem: str):
    current = PurePosixPath(row["normalized_relative_path"])
    name = stem + current.suffix
    max_bytes = os.fpathconf(parent, "PC_NAME_MAX")
    if len(os.fsencode(name)) > (max_bytes if max_bytes > 0 else 255):
        return {"status": "invalid_name"}, None, None, None
    if name == current.name:
        return {"status": "same_name"}, None, None, None
    proposed = current.with_name(name).as_posix()
    if connection.execute(
        """SELECT 1 FROM file_location
        WHERE library_root_id=? AND normalized_relative_path=?
          AND availability<>'missing'""",
        (row["library_root_id"], proposed),
    ).fetchone():
        return {"status": "name_taken"}, None, None, None
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        return {"status": "name_taken"}, None, None, None
    directories.check()
    source = os.stat(current.name, dir_fd=parent, follow_symlinks=False)
    if (source.st_dev, source.st_ino, source.st_ctime_ns) != (
        observed.st_dev,
        observed.st_ino,
        observed.st_ctime_ns,
    ):
        return {"status": "source_unavailable"}, None, None, None
    return None, current, name, proposed


def preview_rename(connection, asset_id: str, location_id: str, stem: object) -> dict:
    if not _valid_stem(stem):
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
            rejection, current, _name, proposed = _check_rename_target(
                connection, row, directories, parent, observed, stem
            )
            if rejection is not None:
                return rejection
            return {
                "status": "ready",
                "current_relative_path": current.as_posix(),
                "proposed_relative_path": proposed,
            }
    except LibraryError:
        return {"status": "source_unavailable"}
    except ValueError:
        return {"status": "invalid_name"}


def apply_rename(session, asset_id: str, location_id: str, stem: object) -> dict:
    if not _valid_stem(stem):
        return {"status": "invalid_name"}

    try:
        with held_location(session.query_connection, asset_id, location_id=location_id) as (
            row,
            directories,
            parent,
            _fd,
            observed,
            _path,
        ):
            if observed.st_nlink != 1:
                return {"status": "source_unavailable"}
            rejection, current, name, proposed = _check_rename_target(
                session.query_connection, row, directories, parent, observed, stem
            )
            if rejection is not None:
                return rejection
            try:
                os.link(
                    current.name,
                    name,
                    src_dir_fd=parent,
                    dst_dir_fd=parent,
                    follow_symlinks=False,
                )
            except FileExistsError:
                return {"status": "name_taken"}
            except OSError:
                return {"status": "source_unavailable"}

            unlinked_old = False
            try:
                directories.check()
                linked = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (
                    linked.st_dev != observed.st_dev
                    or linked.st_ino != observed.st_ino
                    or linked.st_size != observed.st_size
                    or linked.st_mtime_ns != observed.st_mtime_ns
                ):
                    raise LibraryError("unsafe_location")
                observed_at = datetime.now(UTC).isoformat()
                with session.command_connection() as write_connection:
                    write_connection.execute("BEGIN IMMEDIATE")
                    try:
                        current_row = write_connection.execute(
                            """SELECT normalized_relative_path, availability, filesystem_id
                            FROM file_location
                            WHERE id=? AND asset_id=? AND library_root_id=?""",
                            (location_id, asset_id, row["library_root_id"]),
                        ).fetchone()
                        if current_row is None or tuple(current_row) != (
                            current.as_posix(),
                            "present",
                            row["filesystem_id"],
                        ):
                            raise LibraryError("unsafe_location")
                        if write_connection.execute(
                            """SELECT 1 FROM file_location
                            WHERE library_root_id=? AND normalized_relative_path=?
                              AND availability<>'missing'""",
                            (row["library_root_id"], proposed),
                        ).fetchone():
                            raise FileExistsError
                        os.unlink(current.name, dir_fd=parent)
                        unlinked_old = True
                        write_connection.execute(
                            """UPDATE file_location
                            SET normalized_relative_path=?, last_seen_at=?
                            WHERE id=?""",
                            (proposed, observed_at, location_id),
                        )
                        write_connection.commit()
                    except Exception:
                        write_connection.rollback()
                        raise
            except FileExistsError:
                if not unlinked_old:
                    with suppress(OSError):
                        os.unlink(name, dir_fd=parent)
                return {"status": "name_taken"}
            except Exception:
                if unlinked_old:
                    with suppress(OSError):
                        os.link(
                            name,
                            current.name,
                            src_dir_fd=parent,
                            dst_dir_fd=parent,
                            follow_symlinks=False,
                        )
                        os.unlink(name, dir_fd=parent)
                else:
                    with suppress(OSError):
                        os.unlink(name, dir_fd=parent)
                return {"status": "source_unavailable"}
            return {
                "status": "applied",
                "current_relative_path": current.as_posix(),
                "proposed_relative_path": proposed,
            }
    except LibraryError:
        return {"status": "source_unavailable"}
    except ValueError:
        return {"status": "invalid_name"}
