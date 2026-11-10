"""Bounded periodic additions from registered folders, with independent finite workers."""

import os
import time
from pathlib import Path
from uuid import uuid4

from ..catalog_ingestion.media import _Directories
from ..catalog_ingestion.root_grants import RootGrantService, _HeldRoot
from ..library import LibraryError, LibrarySession


def directory_signature(path, anchor):
    """Read directory metadata only; unchanged folders do not reread image contents."""
    held = _HeldRoot(Path(path))
    directories = _Directories()
    count = 0
    result = []
    try:
        if list(anchor) != [path, held.identity.device, held.identity.file_id]:
            raise LibraryError("root_changed")

        def walk(fd, relative, depth):
            nonlocal count
            if depth > 32 or len(directories.fds) > 240:
                raise LibraryError("resource_limit")
            info = os.fstat(fd)
            result.append((relative, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns))
            with os.scandir(fd) as entries:
                children = []
                for item in entries:
                    count += 1
                    if count > 2000:
                        raise LibraryError("resource_limit")
                    children.append(item)
                children.sort(key=lambda item: item.name)
            for item in children:
                if item.is_dir(follow_symlinks=False):
                    child = directories.child(fd, item.name, held.mount)
                    walk(child, relative + "/" + item.name, depth + 1)

        walk(held.fd, "", 0)
        directories.check()
        held.check()
        return tuple(result)
    finally:
        directories.close()
        held.close()


class FolderIndexer:
    def __init__(self, active, state, protected_paths, *, interval=10):
        self.active = active
        self.binding = active.catalog_binding
        self.state_file = state
        self.protected_paths = protected_paths
        self.interval = interval
        self.due = 0
        self.allowed = False
        self.blocked = False
        self.context = None
        self.signatures = {}
        self.queue = []
        self.revision = 0
        self.added = 0
        self.error = None
        self.last_check = None

    @property
    def busy(self):
        return self.context is not None

    def pulse(self, allowed):
        self.allowed = allowed
        self.tick()
        return self.status()

    def status(self):
        return {
            "state": "paused"
            if not self.allowed
            else "updating"
            if self.busy
            else "error"
            if self.error
            else "idle",
            "busy": self.busy,
            "revision": self.revision,
            "added_count": self.added,
            "error": self.error,
            "last_check": self.last_check,
        }

    def refresh(self):
        self.signatures.clear()
        self.due = 0
        return self.status()

    def _close(self):
        if self.context:
            c = self.context
            if not c["service"].close(timeout=0):
                return False
            c["session"].close()
            self.context = None
        return True

    def _next(self):
        if not self.queue:
            self.last_check = time.time()
            self.due = time.monotonic() + self.interval
            return
        root = self.queue.pop(0)
        anchor = self.state_file.get(self.active, root)
        if (
            root in self.signatures
            and anchor is not None
            and directory_signature(anchor[0], anchor) == self.signatures[root]
        ):
            if not self.queue:
                self.last_check = time.time()
                self.due = time.monotonic() + self.interval
            return
        child = LibrarySession.open(self.binding[0])
        try:
            service = RootGrantService(child, str(uuid4()), protected_paths=self.protected_paths)
        except Exception:
            child.close()
            raise
        self.context = {
            "session": child,
            "service": service,
            "root": root,
            "phase": "select",
            "batches": 0,
            "ids": [],
            "cursor": None,
        }

    def tick(self):
        try:
            if self.active.catalog_binding != self.binding:
                raise LibraryError("stale_session")
            if self.context:
                self.context["service"].tick()
                if self.context["phase"] in ("closing", "closing_next"):
                    advance = self.context["phase"] == "closing_next"
                    if self._close() and advance:
                        self._next()
                    return
                if not self.allowed and self.context["phase"] != "apply":
                    self._close()
                    self.queue = []
                    self.due = time.monotonic() + self.interval
                    return
            if (self.blocked or not self.allowed) and (
                not self.context or self.context["phase"] != "apply"
            ):
                return
            if self.context is None:
                if time.monotonic() < self.due:
                    return
                if not self.queue:
                    rows = self.active.query_connection.execute(
                        "SELECT id FROM library_root WHERE availability='available' "
                        "ORDER BY id LIMIT 2001"
                    ).fetchall()
                    if len(rows) > 2000:
                        raise LibraryError("resource_limit")
                    self.queue = [row[0] for row in rows]
                    self.error = None
                self._next()
                return
            c = self.context
            service = c["service"]
            if c["phase"] == "select":
                if c["batches"] >= 21:
                    raise LibraryError("resource_limit")
                anchor = self.state_file.get(self.active, c["root"])
                grant = service.select_monitored(c["root"], anchor)
                if anchor is None:
                    self.state_file.remember(self.active, c["root"], service.binding(c["root"]))
                current_binding = service.binding(c["root"])
                c["signature"] = directory_signature(
                    current_binding[0],
                    [current_binding[0], current_binding[1].device, current_binding[1].file_id],
                )
                c["operation"] = service.prepare(
                    {
                        "session_id": service.session_id,
                        "window_id": service.window_id,
                        "root_grant_id": grant["root_grant_id"],
                        "recursive": True,
                        "client_request_id": str(uuid4()),
                    }
                )["operation_id"]
                c["phase"] = "prepare"
            elif c["phase"] == "prepare":
                result = service.preparation.status(
                    service.session_id, service.window_id, c["operation"]
                )
                if result["state"] == "completed":
                    c.update(
                        phase="page", proposal=result["proposal_id"], ids=[], cursor=None, pages=0
                    )
                elif result["state"] in ("failed", "cancelled"):
                    raise LibraryError(result.get("terminal_reason") or "unavailable")
            elif c["phase"] == "page":
                c["pages"] += 1
                if c["pages"] > 40:
                    raise LibraryError("resource_limit")
                result = service.preparation.page(
                    service.session_id, service.window_id, c["proposal"], c["cursor"], 50
                )
                c["ids"].extend(
                    item["candidate_id"]
                    for item in result["items"]
                    if item.get("selectable") and len(c["ids"]) < 100
                )
                c["ids"] = c["ids"][:100]
                if len(c["ids"]) >= 100 or not result["next_cursor"]:
                    if not c["ids"]:
                        self.signatures[c["root"]] = c["signature"]
                        if len(self.signatures) > 32:
                            self.signatures.pop(next(iter(self.signatures)))
                        c["phase"] = "closing_next"
                        if self._close():
                            self._next()
                    else:
                        command = service.apply(
                            {
                                "session_id": service.session_id,
                                "window_id": service.window_id,
                                "proposal_id": c["proposal"],
                                "candidate_ids": c["ids"],
                                "client_request_id": str(uuid4()),
                            }
                        )
                        c.update(phase="apply", command=command["command_id"])
                else:
                    c["cursor"] = result["next_cursor"]
            elif c["phase"] == "apply":
                result = service.application_status(
                    service.session_id, service.window_id, c["command"]
                )
                if result["state"] in ("queued", "running"):
                    return
                if result["state"] == "outcome_unknown":
                    self.blocked = True
                    raise LibraryError("outcome_unknown")
                if result["state"] != "completed" or result["result"]["status"] != "applied":
                    raise LibraryError("catalog_changed")
                count = sum(item["disposition"] == "created" for item in result["result"]["items"])
                self.added += count
                if count:
                    self.revision += 1
                c["batches"] += 1
                c["phase"] = "select"
                if not self.allowed:
                    self._close()
                    self.queue = []
                    self.due = time.monotonic() + self.interval
        except Exception as error:
            self.error = getattr(error, "code", "unavailable")
            if self.context:
                self.context["phase"] = "closing"
            self._close()
            if self.blocked:
                self.queue = []
            self.due = time.monotonic() + (0 if self.queue else self.interval)

    def shutdown(self):
        self.allowed = False
        self.queue = []
        return self._close()
