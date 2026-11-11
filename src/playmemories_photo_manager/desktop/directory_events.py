"""Linux directory notifications. Events only request a fresh confined scan."""

import ctypes
import os
import sys

# Linux inotify ABI. Open/access/read events are intentionally omitted.
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
WATCH_MASK = (
    IN_ATTRIB
    | IN_CLOSE_WRITE
    | IN_MOVED_FROM
    | IN_MOVED_TO
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MOVE_SELF
)


class DirectoryEvents:
    def __init__(self):
        self.fd = -1
        if sys.platform == "linux":
            libc = ctypes.CDLL(None, use_errno=True)
            self._add = libc.inotify_add_watch
            self.fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)

    def add(self, directory_fd):
        if self.fd < 0:
            return
        # The descriptor is already confined by the scanner. Never use an event path.
        if self._add(self.fd, os.fsencode(f"/proc/self/fd/{directory_fd}"), WATCH_MASK) < 0:
            self.close()

    def changed(self):
        if self.fd < 0:
            return False
        try:
            # Any event, including queue overflow or watch invalidation, requests a scan.
            return bool(os.read(self.fd, 65536))
        except BlockingIOError:
            return False
        except OSError:
            self.close()
            return True

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
