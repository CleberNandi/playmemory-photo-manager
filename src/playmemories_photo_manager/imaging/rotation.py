"""Explicit bounded edits, filesystem publication and catalog reconciliation."""

import json
import os
import stat
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..catalog_ingestion.media import _Directories, _file_state
from ..desktop.media_location import held_location
from ..library import LibraryError


def _same(parent, name, expected):
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    return stat.S_ISREG(info.st_mode) and _file_state(info)[:4] == _file_state(expected)[:4]


def _catalog_identity(path, identity):
    """Check the retained database identity during our own rollback-journal transaction."""
    directories = _Directories()
    try:
        parent = directories.start()
        for component in path.parts[1:-1]:
            parent = directories.child(parent, component)
        info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or (info.st_dev, info.st_ino) != identity
            or info.st_nlink != 1
        ):
            raise LibraryError("unsafe_location")
        directories.check()
        parent_info = os.fstat(parent)
        return parent_info.st_dev, parent_info.st_ino
    finally:
        directories.close()


class RotationService:
    def __init__(self):
        self.job = None
        self.pending = None
        self.blocked = False

    @property
    def busy(self):
        return self.pending is not None

    def start(self, active, asset_id, angle, mode, target, request_id):
        if self.job and self.job["job_id"] == request_id:
            return dict(self.job)
        if self.busy or self.blocked:
            raise LibraryError("busy")
        if type(angle) is not int or angle not in (90, 180, 270) or mode not in ("replace", "copy"):
            raise LibraryError("invalid_request")
        stack = ExitStack()
        output = None
        temporary = None
        parent = None
        try:
            row, directories, parent, source, info, path = stack.enter_context(
                held_location(active.query_connection, asset_id)
            )
            if not 0 < info.st_size <= 64 * 1024 * 1024:
                raise LibraryError("unavailable")
            asset = active.query_connection.execute(
                "SELECT media_type FROM asset WHERE id=? AND kind='photo'", (asset_id,)
            ).fetchone()
            if asset is None or asset[0] not in ("image/png", "image/jpeg"):
                raise LibraryError("unsupported_format")
            if mode == "replace":
                count = active.query_connection.execute(
                    "SELECT count(*) FROM file_location WHERE asset_id=?", (asset_id,)
                ).fetchone()[0]
                if (
                    target is not None
                    or info.st_nlink != 1
                    or count != 1
                    or info.st_uid != os.getuid()
                    or info.st_mode & 0o7000
                    or "system.posix_acl_access" in os.listxattr(source)
                ):
                    raise LibraryError("unsafe_location")
                destination = path.name
            else:
                if not isinstance(target, str) or len(target) > 4096 or "\0" in target:
                    raise LibraryError("invalid_request")
                chosen = Path(target)
                if str(chosen) != target or chosen.parent != path.parent or chosen == path:
                    raise LibraryError("unsafe_location")
                suffixes = (".png",) if asset[0] == "image/png" else (".jpg", ".jpeg", ".jpe")
                if chosen.suffix.lower() not in suffixes or len(chosen.name.encode()) > 240:
                    raise LibraryError("invalid_request")
                destination = chosen.name
                try:
                    os.stat(destination, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise LibraryError("already_exists")
            temporary = f".playmemories-edit-{request_id}.tmp"
            output = os.open(
                temporary, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent
            )
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "playmemories_photo_manager.imaging.rotate_worker",
                    str(source),
                    str(output),
                    str(os.getpid()),
                    str(angle),
                ],
                pass_fds=(source, output),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                    "LANG": "C.UTF-8",
                    "OMP_NUM_THREADS": "1",
                },
            )
            self.job = {
                "job_id": request_id,
                "asset_id": asset_id,
                "state": "running",
                "result_asset_id": None,
                "error": None,
            }
            self.pending = (
                active,
                row,
                directories,
                parent,
                source,
                info,
                path,
                destination,
                temporary,
                output,
                process,
                stack,
                time.monotonic() + 18,
                mode,
                angle,
            )
            return dict(self.job)
        except Exception:
            if output is not None:
                os.close(output)
            if temporary is not None and parent is not None:
                os.unlink(temporary, dir_fd=parent)
            stack.close()
            raise

    def tick(self):
        if self.pending is None:
            return
        (
            active,
            row,
            directories,
            parent,
            source,
            before,
            path,
            destination,
            temporary,
            output,
            process,
            stack,
            deadline,
            mode,
            angle,
        ) = self.pending
        if process.poll() is None:
            if time.monotonic() > deadline:
                process.kill()
            return
        published = False
        commit_attempted = False
        backup = None
        receipt = None
        after = None
        connection = None
        try:
            if process.returncode != 0:
                raise LibraryError(
                    "unsupported_format" if process.returncode == 3 else "unavailable"
                )
            after = os.fstat(output)
            if not 0 < after.st_size <= 64 * 1024 * 1024 or not _same(parent, temporary, after):
                raise LibraryError("unsafe_location")
            directories.check()
            if not _same(parent, path.name, before) or _file_state(os.fstat(source)) != _file_state(
                before
            ):
                raise LibraryError("unsafe_location")
            catalog_path, catalog_identity = active.catalog_binding
            catalog_parent = _catalog_identity(catalog_path, catalog_identity)
            with active.command_connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute(
                    "SELECT * FROM file_location WHERE id=?", (row["id"],)
                ).fetchone()
                if current is None or tuple(current) != tuple(row)[: len(current)]:
                    raise LibraryError("stale_session")
                now = datetime.now(UTC).isoformat()
                if mode == "replace":
                    backup = f".playmemories-before-{self.job['job_id']}.bak"
                    os.link(
                        path.name,
                        backup,
                        src_dir_fd=parent,
                        dst_dir_fd=parent,
                        follow_symlinks=False,
                    )
                    if not _same(parent, backup, before) or not _same(parent, path.name, before):
                        raise LibraryError("unsafe_location")
                    receipt_name = f".playmemories-before-{self.job['job_id']}.json"
                    receipt_fd = os.open(
                        receipt_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=parent,
                    )
                    receipt = (receipt_name, os.fstat(receipt_fd))
                    with os.fdopen(receipt_fd, "w", encoding="utf8") as receipt_file:
                        json.dump(
                            {
                                "version": 1,
                                "job_id": self.job["job_id"],
                                "asset_id": row["asset_id"],
                                "source_name": path.name,
                                "backup_name": backup,
                                "angle": angle,
                                "before": _file_state(before),
                                "encoded": _file_state(after),
                            },
                            receipt_file,
                        )
                        receipt_file.flush()
                        os.fsync(receipt_file.fileno())
                    os.fsync(parent)
                    os.fchown(output, before.st_uid, before.st_gid)
                    os.fchmod(output, stat.S_IMODE(before.st_mode) & 0o777)
                    os.fsync(output)
                    os.replace(temporary, destination, src_dir_fd=parent, dst_dir_fd=parent)
                    published = True
                    result_id = row["asset_id"]
                    connection.execute(
                        "UPDATE asset SET byte_size=?,sha256=NULL,hash_state='absent' WHERE id=?",
                        (after.st_size, result_id),
                    )
                    connection.execute(
                        "UPDATE file_location SET "
                        "filesystem_id=?,observed_byte_size=?,observed_mtime_ns=?,"
                        "last_seen_at=? WHERE id=?",
                        (
                            f"scanner:{after.st_dev}:{after.st_ino}",
                            after.st_size,
                            after.st_mtime_ns,
                            now,
                            row["id"],
                        ),
                    )
                else:
                    relative = str(Path(row["normalized_relative_path"]).with_name(destination))
                    if connection.execute(
                        "SELECT 1 FROM file_location WHERE library_root_id=? AND "
                        "normalized_relative_path=?",
                        (row["library_root_id"], relative),
                    ).fetchone():
                        raise LibraryError("already_exists")
                    os.link(
                        temporary,
                        destination,
                        src_dir_fd=parent,
                        dst_dir_fd=parent,
                        follow_symlinks=False,
                    )
                    published = True
                    result_id = str(uuid4())
                    media = connection.execute(
                        "SELECT media_type FROM asset WHERE id=?", (row["asset_id"],)
                    ).fetchone()[0]
                    connection.execute(
                        "INSERT INTO asset(id,kind,byte_size,media_type) VALUES (?,'photo',?,?)",
                        (result_id, after.st_size, media),
                    )
                    connection.execute(
                        """INSERT INTO file_location(id,asset_id,library_root_id,
                        normalized_relative_path,entry_type,filesystem_id,observed_byte_size,
                        observed_mtime_ns,availability,last_seen_at)
                        VALUES (?,?,?,?,'file',?,?,?,'present',?)""",
                        (
                            str(uuid4()),
                            result_id,
                            row["library_root_id"],
                            relative,
                            f"scanner:{after.st_dev}:{after.st_ino}",
                            after.st_size,
                            after.st_mtime_ns,
                            now,
                        ),
                    )
                    from types import SimpleNamespace

                    from ..catalog_ingestion.capture import extract_capture, persist_capture

                    os.lseek(output, 0, os.SEEK_SET)
                    with os.fdopen(os.dup(output), "rb") as reader:
                        observations = extract_capture(reader)
                    registration = SimpleNamespace(
                        disposition=SimpleNamespace(value="created"),
                        asset=SimpleNamespace(id=result_id),
                        location=SimpleNamespace(normalized_relative_path=relative),
                    )
                    persist_capture(connection, [registration], {relative: observations})
                os.fsync(parent)
                directories.check()
                if not _same(parent, destination, after):
                    raise LibraryError("unsafe_location")
                connection.execute(
                    """INSERT INTO metadata(id,asset_id,namespace,metadata_key,source,
                    source_key,raw_value,extractor_version,extracted_at)
                    VALUES (?,?,'catalog','rotation','explicit-user-edit',?,?,'rotation/1',?)""",
                    (
                        str(uuid4()),
                        result_id,
                        self.job["job_id"],
                        json.dumps(
                            {"angle": angle, "mode": mode, "source_asset_id": row["asset_id"]}
                        ),
                        now,
                    ),
                )
                if _catalog_identity(catalog_path, catalog_identity) != catalog_parent:
                    raise LibraryError("unsafe_location")
                commit_attempted = True
                connection.commit()
            self.job.update(state="completed", result_asset_id=result_id)
            if backup:
                if not _same(parent, backup, before):
                    raise LibraryError("unsafe_location")
                os.unlink(backup, dir_fd=parent)
                backup = None
            if receipt:
                receipt_info = os.stat(receipt[0], dir_fd=parent, follow_symlinks=False)
                if (receipt_info.st_dev, receipt_info.st_ino) != (
                    receipt[1].st_dev,
                    receipt[1].st_ino,
                ):
                    raise LibraryError("unsafe_location")
                os.unlink(receipt[0], dir_fd=parent)
                receipt = None
            os.fsync(parent)
        except Exception as error:
            # A failed commit acknowledgement cannot prove whether the catalog committed.
            if published and not commit_attempted:
                try:
                    if _same(parent, destination, after):
                        if backup and _same(parent, backup, before):
                            os.replace(backup, destination, src_dir_fd=parent, dst_dir_fd=parent)
                            backup = None
                        elif mode == "copy":
                            os.unlink(destination, dir_fd=parent)
                        else:
                            raise LibraryError("outcome_unknown")
                        os.fsync(parent)
                        published = False
                except Exception:
                    pass
            code = "outcome_unknown" if published else getattr(error, "code", "unavailable")
            self.job.update(state="outcome_unknown" if published else "failed", error=code)
            self.blocked = published
        finally:
            if backup and not published:
                try:
                    if _same(parent, backup, before):
                        os.unlink(backup, dir_fd=parent)
                except OSError:
                    pass
            if receipt and not published:
                try:
                    current_receipt = os.stat(receipt[0], dir_fd=parent, follow_symlinks=False)
                    if (current_receipt.st_dev, current_receipt.st_ino) == (
                        receipt[1].st_dev,
                        receipt[1].st_ino,
                    ):
                        os.unlink(receipt[0], dir_fd=parent)
                except OSError:
                    pass
            try:
                if _same(parent, temporary, os.fstat(output)):
                    os.unlink(temporary, dir_fd=parent)
            except OSError:
                pass
            os.close(output)
            stack.close()
            self.pending = None

    def status(self, job_id):
        self.tick()
        if self.job is None or self.job["job_id"] != job_id:
            raise LibraryError("not_found")
        return dict(self.job)

    def shutdown(self):
        if not self.busy:
            return True
        process = self.pending[10]
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        self.tick()
        return not self.busy
