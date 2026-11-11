"""Privileged, volatile root selections. No renderer route or native dialog is enabled here."""

from __future__ import annotations

import errno
import json
import os
import sqlite3
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from ..catalog import Catalog, LibraryRoot
from ..catalog.errors import CatalogError, CatalogStateConflictError
from ..catalog.repository import CatalogRepository
from ..library import LibraryError, LibrarySession, read_library_connection
from ..scanner import PhysicalIdentity
from .application_commands import ApplicationCommands
from .application_supervisor import ApplicationSupervisor
from .media import _Changed, _Directories, _identity, _mount_id
from .preparation import PreparationController, PreparationError, PreparationInput, _uuid

MAX_ROOTS = 2000
MAX_GRANTS = 32
MAX_HELD_FDS = 256
MAX_BYTES = 8 * 1024 * 1024


def _path(raw: object) -> Path:
    if not isinstance(raw, str) or not 1 <= len(raw) <= 4096 or "\0" in raw:
        raise PreparationError("invalid_request")
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts or str(path) != raw:
        raise PreparationError("invalid_request")
    return path


@contextmanager
def _sanitize():
    try:
        yield
    except LibraryError as error:
        raise PreparationError(error.code) from None
    except CatalogStateConflictError:
        raise PreparationError("root_changed") from None
    except CatalogError as error:
        cause = error.__cause__
        reason = "root_changed"
        if getattr(cause, "sqlite_errorcode", 0) & 255 == sqlite3.SQLITE_TOOBIG:
            reason = "resource_limit"
        raise PreparationError(reason) from None
    except _Changed:
        raise PreparationError("root_changed") from None
    except sqlite3.Error as error:
        code = getattr(error, "sqlite_errorcode", 0) & 255
        reason = "resource_limit" if code == sqlite3.SQLITE_TOOBIG else "root_changed"
        raise PreparationError(reason) from None
    except PermissionError:
        raise PreparationError("permission_denied") from None
    except OSError as error:
        if error.errno in (errno.EMFILE, errno.ENFILE, errno.ENOMEM):
            reason = "resource_limit"
        elif error.errno in (errno.ELOOP, errno.ENOTDIR):
            reason = "unsafe_location"
        else:
            reason = "root_changed"
        raise PreparationError(reason) from None


class _HeldRoot:
    def __init__(self, path: Path):
        self.path = path
        self.directories = _Directories()
        try:
            self.fd = self.directories.start()
            for part in path.parts[1:]:
                if len(self.directories.fds) == MAX_HELD_FDS:
                    raise PreparationError("resource_limit")
                self.fd = self.directories.child(self.fd, part)
            self.identity = _identity(os.fstat(self.fd))
            self.mount = _mount_id(self.fd)
            self.ancestors = {_identity(os.fstat(fd)) for fd in self.directories.fds}
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        self.directories.check()
        if _identity(os.fstat(self.fd)) != self.identity or _mount_id(self.fd) != self.mount:
            raise PreparationError("root_changed")

    def close(self):
        self.directories.close()


@dataclass
class _Grant:
    root: LibraryRoot
    held: _HeldRoot
    expires: float
    diagnostics: tuple[str, ...]
    anchored: bool = False
    monitored: bool = False


class RootGrantService:
    """One library session/window owner. Paths are supplied only by trusted native selection.

    Future bridge composition must pump tick even while idle. Session.close invokes a
    guard that revokes grants immediately and refuses closure until worker reap.
    """

    def __init__(
        self, session: LibrarySession, window_id: str, *, protected_paths: tuple[Path, ...]
    ):
        _uuid(window_id)
        if not isinstance(protected_paths, tuple) or any(
            not isinstance(p, Path) for p in protected_paths
        ):
            raise PreparationError("invalid_request")
        self._protected = tuple(_path(str(p)) for p in protected_paths)
        with _sanitize():
            self._catalog, self._catalog_identity = session.catalog_binding
        self.session = session
        self.session_id = session.descriptor.session_id
        self.window_id = window_id
        self._owner = threading.get_ident()
        self._closed = False
        self._grants: dict[str, _Grant] = {}
        self._bindings = {}
        self._admissions = {}
        self.preparation = PreparationController(self.session_id, window_id)
        self.commands = ApplicationCommands(
            self.session_id,
            window_id,
            active_guard=self._require,
            resolve_proposal=self._application_source,
            validate_source=self._application_binding,
        )
        self.application = ApplicationSupervisor(self.commands)
        try:
            session._bind_close_guard(self._before_session_close)
        except BaseException:
            self.preparation.shutdown()
            self.application.shutdown()
            raise

    def _require(self):
        if threading.get_ident() != self._owner:
            raise PreparationError("invalid_request")
        if self._closed:
            raise PreparationError("stale_session")
        with _sanitize():
            self.session._require_active()
        self._expire()

    def _catalog_check(self):
        with _sanitize():
            if self.session.catalog_binding != (self._catalog, self._catalog_identity):
                raise PreparationError("root_changed")

    def _params(self, params, fields):
        self._require()
        if not isinstance(params, dict) or set(params) != set(fields):
            raise PreparationError("invalid_request")
        _uuid(params["session_id"])
        _uuid(params["window_id"])
        if params["session_id"] != self.session_id or params["window_id"] != self.window_id:
            raise PreparationError("stale_session")
        if params["recursive"] is not True:
            raise PreparationError("invalid_request")

    def _application_source(self, proposal_id):
        return self.preparation.application_source(self.session_id, self.window_id, proposal_id)

    def _application_binding(self, value):
        self._require()
        self._catalog_check()
        if (value.catalog_path, value.catalog_identity) != (
            str(self._catalog),
            self._catalog_identity,
        ):
            raise PreparationError("stale_session")
        expected = (value.root_path, PhysicalIdentity(*value.root_identity), value.mount_id)
        if self._bindings.get(value.root_id) != expected:
            raise PreparationError("stale_session")
        with _sanitize():
            held = _HeldRoot(_path(value.root_path))
            try:
                if (held.identity, held.mount) != expected[1:]:
                    raise PreparationError("root_changed")
                current = self._validate_overlap(held, self._roots())
                if (
                    current is None
                    or current.id != value.root_id
                    or str(current.availability) != "available"
                ):
                    raise PreparationError("root_changed")
            finally:
                held.close()

    def _application_idle(self):
        if self.commands.closing:
            raise PreparationError("stale_session")
        if self.commands.suspended:
            raise PreparationError("outcome_unknown")
        if self.commands.busy:
            raise PreparationError("busy")

    def _expire(self):
        for identifier, grant in tuple(self._grants.items()):
            if time.monotonic() >= grant.expires:
                grant.held.close()
                del self._grants[identifier]

    def _roots(self):
        roots, size = [], 0
        with read_library_connection(
            self._catalog, expected_identity=self._catalog_identity
        ) as connection:
            connection.execute("BEGIN")
            try:
                repository = CatalogRepository(connection)
                while True:
                    page = repository.list_roots(min(100, MAX_ROOTS + 1 - len(roots)), len(roots))
                    for root in page:
                        if len(roots) == MAX_ROOTS:
                            raise PreparationError("resource_limit")
                        _path(root.normalized_path)
                        size += len(json.dumps(asdict(root), ensure_ascii=True).encode())
                        if size > MAX_BYTES:
                            raise PreparationError("resource_limit")
                        roots.append(root)
                    if len(page) < 100:
                        break
            finally:
                connection.rollback()
        return tuple(roots)

    def _validate_overlap(self, held, roots):
        protected = (
            self._catalog,
            *(Path(str(self._catalog) + suffix) for suffix in ("-journal", "-wal", "-shm")),
            *self._protected,
        )
        for destination in protected:
            if destination.is_relative_to(held.path) or held.path.is_relative_to(destination):
                raise PreparationError("unsafe_location")
            # Compare existing ancestors too, so a bind alias cannot hide catalog/cache containment.
            ancestor = destination
            while True:
                try:
                    info = os.lstat(ancestor)
                    break
                except FileNotFoundError:
                    if ancestor == ancestor.parent:
                        raise
                    ancestor = ancestor.parent
            if stat.S_ISLNK(info.st_mode):
                raise PreparationError("unsafe_location")
            is_directory = stat.S_ISDIR(info.st_mode)
            parent = ancestor if is_directory else ancestor.parent
            protect_subtree = is_directory and ancestor == destination
            protected_root = _HeldRoot(parent)
            try:
                if (
                    held.identity in protected_root.ancestors
                    or protect_subtree
                    and protected_root.identity in held.ancestors
                    or held.identity.device == protected_root.identity.device
                    and held.mount != protected_root.mount
                ):
                    raise PreparationError("unsafe_location")
            finally:
                protected_root.close()
        same = None
        for root in roots:
            path = _path(root.normalized_path)
            if path == held.path:
                same = root
                continue
            if path.is_relative_to(held.path) or held.path.is_relative_to(path):
                raise PreparationError("unsafe_location")
            try:
                other = _HeldRoot(path)
            except FileNotFoundError:
                continue  # A missing, lexically disjoint path has no current physical alias.
            try:
                if (
                    held.identity in other.ancestors
                    or other.identity in held.ancestors
                    or (held.identity.device == other.identity.device and held.mount != other.mount)
                ):
                    raise PreparationError("unsafe_location")
            finally:
                other.close()
        held.check()
        return same

    def _known_locations(self, held, root_id):
        # Materialize bounded database observations and close SQLite before metadata checks.
        locations, size = [], 0
        with read_library_connection(
            self._catalog, expected_identity=self._catalog_identity
        ) as connection:
            connection.execute("BEGIN")
            try:
                for location in CatalogRepository(connection).iter_root_locations(root_id, 2001, 0):
                    if len(locations) == 2000:
                        raise PreparationError("resource_limit")
                    size += len(json.dumps(asdict(location), ensure_ascii=True).encode())
                    if size > MAX_BYTES:
                        raise PreparationError("resource_limit")
                    locations.append(location)
            finally:
                connection.rollback()
        for location in locations:
            if location.availability == "missing":
                continue
            if len(location.normalized_relative_path) > 4096:
                raise PreparationError("resource_limit")
            relative = PurePosixPath(location.normalized_relative_path)
            if len(relative.parts) > 32:
                raise PreparationError("resource_limit")
            if (
                relative.is_absolute()
                or not relative.parts
                or any(p in (".", "..") for p in relative.parts)
                or str(relative) != location.normalized_relative_path
            ):
                raise PreparationError("root_changed")
            parents = _Directories()
            try:
                parent = held.fd
                for part in relative.parts[:-1]:
                    parent = parents.child(parent, part, held.mount)
                fd = os.open(relative.name, os.O_PATH | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    info = os.fstat(fd)
                    identity = f"scanner:{info.st_dev}:{info.st_ino}"
                    expected_type = stat.S_ISREG if location.entry_type == "file" else stat.S_ISLNK
                    if (
                        not expected_type(info.st_mode)
                        or _mount_id(fd) != held.mount
                        or location.filesystem_id is not None
                        and location.filesystem_id != identity
                        or location.observed_byte_size is not None
                        and location.observed_byte_size != info.st_size
                        or location.observed_mtime_ns is not None
                        and location.observed_mtime_ns != info.st_mtime_ns
                    ):
                        raise PreparationError("root_changed")
                    if _identity(
                        os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
                    ) != _identity(info):
                        raise PreparationError("root_changed")
                    parents.check()
                finally:
                    os.close(fd)
            finally:
                parents.close()
        held.check()

    def select(self, params: object) -> dict:
        """Only after both trusted native dialogs confirmed. Cancellation never calls this."""
        self._params(params, ("session_id", "window_id", "path", "recursive", "identity_reviewed"))
        if params["identity_reviewed"] is not True:
            raise PreparationError("invalid_request")
        return self._select(_path(params["path"]))

    def _select(self, path, *, expected=None, monitored=False):
        self._application_idle()
        if self.preparation.busy:
            raise PreparationError("busy")
        self._catalog_check()
        if len(self._grants) >= MAX_GRANTS:
            raise PreparationError("resource_limit")
        held = None
        with _sanitize():
            try:
                held = _HeldRoot(path)
                if (
                    sum(len(g.held.directories.fds) for g in self._grants.values())
                    + len(held.directories.fds)
                    > MAX_HELD_FDS
                ):
                    raise PreparationError("resource_limit")
                if expected is not None and (str(path), held.identity, held.mount) != expected:
                    raise PreparationError("root_changed")
                roots = self._roots()
                existing = self._validate_overlap(held, roots)
                if existing is None and len(roots) == MAX_ROOTS:
                    raise PreparationError("resource_limit")
                diagnostics = ()
                if existing is not None:
                    binding = self._bindings.get(existing.id)
                    if binding is not None and binding != (
                        existing.normalized_path,
                        held.identity,
                        held.mount,
                    ):
                        raise PreparationError("root_changed")
                    if binding is None:
                        diagnostics = ("ROOT_IDENTITY_UNAVAILABLE",)
                    if expected is None:
                        self._known_locations(held, existing.id)
                held.check()
                if len(self._bindings) >= MAX_ROOTS and (
                    existing is None or existing.id not in self._bindings
                ):
                    raise PreparationError("resource_limit")
                with self.session.command_connection() as connection:
                    connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_BYTES)
                    root = Catalog(connection).register_reviewed_root(
                        path.name or "/", str(path), expected_roots=roots
                    )
                held.check()
                identifier = str(uuid4())
                self._bindings[root.id] = (root.normalized_path, held.identity, held.mount)
                self._grants[identifier] = _Grant(
                    root, held, time.monotonic() + 300, diagnostics, expected is not None, monitored
                )
                held = None
                return {"root_grant_id": identifier, "root_id": root.id, "expires_in_ms": 300000}
            finally:
                if held is not None:
                    held.close()

    def binding(self, root_id):
        """Private trusted-shell anchor; never a renderer DTO."""
        self._require()
        return self._bindings[root_id]

    def select_monitored(self, root_id, anchor):
        """Fresh one-use grant under the explicit registered-folder monitoring policy."""
        self._require()
        roots = self._roots()
        root = next((item for item in roots if item.id == root_id), None)
        if root is None or str(root.availability) != "available":
            raise PreparationError("root_changed")
        held = _HeldRoot(_path(root.normalized_path))
        try:
            if anchor is None:
                # Legacy catalogs have no persisted root inode. Require a known file witness;
                # the existing admission below verifies all known occurrences before scanning.
                known = self.session.query_connection.execute(
                    "SELECT 1 FROM file_location WHERE library_root_id=? "
                    "AND availability = 'present' AND filesystem_id IS NOT NULL LIMIT 1",
                    (root_id,),
                ).fetchone()
                if known is None:
                    raise PreparationError("root_changed")
            elif list(anchor) != [
                root.normalized_path,
                held.identity.device,
                held.identity.file_id,
            ]:
                raise PreparationError("root_changed")
            expected = (root.normalized_path, held.identity, held.mount)
            held.check()
            result = self._select(
                held.path, expected=expected if anchor is not None else None, monitored=True
            )
            if self._bindings.get(root_id) != expected:
                raise PreparationError("root_changed")
            return result
        finally:
            held.close()

    def prepare(self, params: object) -> dict:
        self._params(
            params, ("session_id", "window_id", "root_grant_id", "recursive", "client_request_id")
        )
        _uuid(params["root_grant_id"])
        _uuid(params["client_request_id"])
        request_id = params["client_request_id"]
        signature = (params["root_grant_id"], params["recursive"])
        if request_id in self._admissions:
            previous, value = self._admissions[request_id]
            if previous != signature:
                raise PreparationError("invalid_request")
            return self.preparation.start(value, request_id)
        self._application_idle()
        if self.preparation.busy:
            raise PreparationError("busy")
        self._catalog_check()
        grant = self._grants.get(params["root_grant_id"])
        if grant is None:
            raise PreparationError("stale_grant")
        with _sanitize():
            try:
                grant.held.check()
                root = self._validate_overlap(grant.held, self._roots())
                if root != grant.root:
                    raise PreparationError("root_changed")
                if not grant.anchored:
                    self._known_locations(grant.held, root.id)
                value = PreparationInput(
                    str(self._catalog),
                    root.normalized_path,
                    root.id,
                    self._catalog_identity,
                    (grant.held.identity.device, grant.held.identity.file_id),
                    grant.held.mount,
                    additions_only=grant.monitored,
                )
                job = self.preparation.start(value, request_id)
            except BaseException:
                # busy/resource refusal before admission still requires a fresh explicit selection.
                self._grants.pop(params["root_grant_id"]).held.close()
                raise
        self._grants.pop(params["root_grant_id"]).held.close()
        self._admissions[request_id] = (signature, value)
        return job

    def apply(self, params):
        value = self.commands.admit(params)
        if value["state"] == "queued":
            identifier = value["command_id"]
            payload = self.commands.claim(self.session_id, self.window_id, identifier)
            try:
                self.application.start(payload, params["client_request_id"])
            except Exception:
                if self.application.busy:
                    self.application._abort("protocol_failure")
                else:
                    self.commands.worker_failed(
                        self.session_id, self.window_id, identifier, reaped=True
                    )
        return self.commands.status(self.session_id, self.window_id, value["command_id"])

    def application_status(self, session_id, window_id, command_id):
        self._require()
        self.application.tick()
        return self.commands.status(session_id, window_id, command_id)

    def tick(self):
        if threading.get_ident() != self._owner:
            raise PreparationError("invalid_request")
        self.preparation.tick()
        self.application.tick()
        self._expire()

    def _before_session_close(self):
        if not self.close(timeout=0):
            raise LibraryError("busy")

    def close(self, timeout=2.5):
        if threading.get_ident() != self._owner:
            raise PreparationError("invalid_request")
        if not self._closed:
            try:
                self.commands.close()
            except PreparationError as error:
                if error.code == "busy":
                    for grant in self._grants.values():
                        grant.held.close()
                    self._grants.clear()
                    self._bindings.clear()
                    self._admissions.clear()
                    self.application.shutdown(timeout=0)
                    return False
                raise
            self.application.shutdown(timeout=0)
            self._closed = True
            for grant in self._grants.values():
                grant.held.close()
            self._grants.clear()
            self._bindings.clear()
            self._admissions.clear()
            return self.preparation.shutdown(timeout=timeout)
        deadline = time.monotonic() + timeout
        while self.preparation.busy and time.monotonic() < deadline:
            self.preparation.tick()
            time.sleep(0.01)
        return not self.preparation.busy
