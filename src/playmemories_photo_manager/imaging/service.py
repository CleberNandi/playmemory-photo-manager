"""Session-owned asynchronous image jobs, with descriptor confinement and bounded RAM cache."""

from __future__ import annotations

import base64
import os
import stat
import subprocess
import sys
import time
from collections import OrderedDict
from pathlib import Path, PurePosixPath

from ..catalog_ingestion.media import _Changed, _Directories, _file_state, _mount_id

MAX_OUTPUT = 160 * 1024


class ImageService:
    def __init__(self):
        self.jobs = {}
        self.cache = OrderedDict()
        self.closed = False

    def request(self, connection, asset_id, variant):
        self.tick()
        if self.closed or variant not in ("grid", "preview"):
            return None
        row = connection.execute(
            """SELECT fl.*,lr.normalized_path FROM file_location fl
            JOIN library_root lr ON lr.id=fl.library_root_id
            WHERE fl.asset_id=? AND fl.entry_type='file' AND fl.availability='present'
            AND lr.availability='available' ORDER BY fl.id LIMIT 1""",
            (asset_id,),
        ).fetchone()
        if row is None or not row["filesystem_id"]:
            return None
        directories = _Directories()
        fd = None
        try:
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
            ):
                return None
            parent = directories.start()
            for component in root.parts[1:]:
                parent = directories.child(parent, component)
            mount = _mount_id(parent)
            for component in relative.parts[:-1]:
                parent = directories.child(parent, component, mount)
            fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            info = os.fstat(fd)
            state = _file_state(info)
            if (
                not stat.S_ISREG(info.st_mode)
                or not 0 < info.st_size <= 64 * 1024 * 1024
                or _mount_id(fd) != mount
                or row["filesystem_id"] != f"scanner:{info.st_dev}:{info.st_ino}"
                or info.st_size != row["observed_byte_size"]
                or info.st_mtime_ns != row["observed_mtime_ns"]
            ):
                return None
            directories.check()
            key = (asset_id, variant, state)
            if key in self.cache:
                result = self.cache[key]
                if result is None:
                    del self.cache[key]  # Consume failure once; a later explicit read may retry.
                else:
                    self.cache.move_to_end(key)
                return result
            if key in self.jobs or len(self.jobs) >= 4:
                return {"status": "pending"}
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "playmemories_photo_manager.imaging.worker",
                    str(fd),
                    str(os.getpid()),
                    variant,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                pass_fds=(fd,),
                close_fds=True,
                start_new_session=True,
                cwd=Path(__file__).resolve().parents[2],
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                    "LANG": "C.UTF-8",
                    "OMP_NUM_THREADS": "1",
                },
            )
            os.set_blocking(process.stdout.fileno(), False)
            self.jobs[key] = (
                process,
                time.monotonic() + 5,
                bytearray(),
                directories,
                fd,
                parent,
                relative.name,
                state,
            )
            directories = None
            fd = None
            return {"status": "pending"}
        except (OSError, RuntimeError, _Changed):
            return None
        finally:
            if fd is not None:
                os.close(fd)
            if directories is not None:
                directories.close()

    def tick(self):
        for key, job in tuple(self.jobs.items()):
            process, deadline, data, directories, fd, parent, name, state = job
            try:
                for _ in range(8):
                    chunk = os.read(process.stdout.fileno(), 32768)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_OUTPUT:
                        break
            except BlockingIOError:
                pass
            if (
                self.closed or time.monotonic() > deadline or len(data) > MAX_OUTPUT
            ) and process.poll() is None:
                process.kill()
            code = process.poll()
            if code is None:
                continue
            # Drain after actual reap, bounded by the same response limit.
            try:
                while len(data) <= MAX_OUTPUT:
                    chunk = os.read(process.stdout.fileno(), 32768)
                    if not chunk:
                        break
                    data.extend(chunk)
            except BlockingIOError:
                pass
            result = None
            try:
                directories.check()
                linked = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (
                    code == 0
                    and 0 < len(data) <= MAX_OUTPUT
                    and state == _file_state(os.fstat(fd)) == _file_state(linked)
                ):
                    result = {
                        "media_type": "image/png" if key[1] == "grid" else "image/jpeg",
                        "base64": base64.b64encode(data).decode("ascii"),
                        "synthetic": False,
                    }
                    if key[1] == "grid":
                        result.update(width=256, height=160)
            except (OSError, RuntimeError, _Changed):
                pass
            finally:
                process.stdout.close()
                os.close(fd)
                directories.close()
                del self.jobs[key]
            self.cache[key] = result
            if len(self.cache) > 32:
                self.cache.popitem(last=False)

    def shutdown(self):
        self.closed = True
        self.cache.clear()
        self.tick()
        return not self.jobs
