"""Private persistent physical anchors for folders explicitly added to a library."""

import json
import os
import stat
from pathlib import Path
from uuid import uuid4

from ..catalog_ingestion.media import _Directories
from ..library import LibraryError

MAX_BYTES = 1024 * 1024


class IndexState:
    def __init__(self, path):
        self.path = Path(path) if path else None

    def _parent(self):
        if self.path is None or not self.path.is_absolute() or ".." in self.path.parts:
            raise LibraryError("unsafe_location")
        directories = _Directories()
        try:
            parent = directories.start()
            for part in self.path.parts[1:-1]:
                parent = directories.child(parent, part)
            info = os.fstat(parent)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise LibraryError("unsafe_location")
            directories.check()
            return directories, parent
        except Exception:
            directories.close()
            raise

    def _read(self, parent):
        try:
            fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            return {}
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_size > MAX_BYTES
            ):
                raise LibraryError("unsafe_location")
            data = json.loads(os.read(fd, MAX_BYTES + 1))
            if (
                not isinstance(data, dict)
                or set(data) != {"version", "roots"}
                or data["version"] != 1
                or not isinstance(data["roots"], dict)
                or len(data["roots"]) > 2000
            ):
                raise LibraryError("unsafe_location")
            for value in data["roots"].values():
                if (
                    not isinstance(value, list)
                    or len(value) != 3
                    or not isinstance(value[0], str)
                    or len(value[0]) > 4096
                    or any(type(v) is not int or v < 0 for v in value[1:])
                ):
                    raise LibraryError("unsafe_location")
            return data["roots"]
        finally:
            os.close(fd)

    def key(self, active, root_id):
        _, identity = active.catalog_binding
        return f"{identity[0]}:{identity[1]}:{root_id}"

    def get(self, active, root_id):
        directories, parent = self._parent()
        try:
            result = self._read(parent).get(self.key(active, root_id))
            directories.check()
            return result
        finally:
            directories.close()

    def remember(self, active, root_id, binding):
        path, identity, _ = binding
        directories, parent = self._parent()
        temporary = f".index-{uuid4()}.tmp"
        created = False
        try:
            roots = self._read(parent)
            key = self.key(active, root_id)
            if key not in roots and len(roots) >= 2000:
                raise LibraryError("resource_limit")
            roots[key] = [path, identity.device, identity.file_id]
            data = json.dumps({"version": 1, "roots": roots}).encode()
            if len(data) > MAX_BYTES:
                raise LibraryError("resource_limit")
            fd = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            created = True
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            directories.check()
            os.replace(temporary, self.path.name, src_dir_fd=parent, dst_dir_fd=parent)
            created = False
            os.fsync(parent)
        finally:
            if created:
                os.unlink(temporary, dir_fd=parent)
            directories.close()
