"""Linux-only lifecycle; never enumerate or open media roots.

Connections stay on the owning thread. The /proc check witnesses the descriptor
actually opened by SQLite, rather than treating database_list as inode evidence.
This is not isolation from hostile processes running as the same user.
"""

from __future__ import annotations

import errno
import os
import sqlite3
import stat
import sys
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..catalog.database import (
    IncompatibleSchemaError,
    UpgradeRequiredError,
    apply_migrations,
    connect,
    validate_database,
)


class LibraryError(RuntimeError):
    """Fixed public code; never contains a path, SQL or underlying message."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SessionDescriptor:
    session_id: str
    display_name: str


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _translate(error: Exception) -> LibraryError:
    if isinstance(error, LibraryError):
        return error
    if isinstance(error, UpgradeRequiredError):
        return LibraryError("upgrade_required")
    if isinstance(error, IncompatibleSchemaError):
        return LibraryError("incompatible")
    if isinstance(error, FileNotFoundError):
        return LibraryError("not_found")
    if isinstance(error, PermissionError):
        return LibraryError("permission_denied")
    if isinstance(error, OSError) and error.errno in (errno.ELOOP, errno.ENOTDIR, errno.EEXIST):
        return LibraryError("unsafe_location")
    if isinstance(error, sqlite3.Error):
        code = getattr(error, "sqlite_errorcode", 0) & 255
        if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            return LibraryError("busy")
        if code in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
            return LibraryError("corrupt")
        if code in (sqlite3.SQLITE_READONLY, sqlite3.SQLITE_PERM, sqlite3.SQLITE_AUTH):
            return LibraryError("permission_denied")
    return LibraryError("internal_error")


class _Selection:
    def __init__(self, path: Path, *, create: bool):
        self.path = path
        self.fds: list[int] = []
        try:
            if sys.platform != "linux" or not Path("/proc/self/fd").is_dir():
                raise LibraryError("unsafe_location")
            if not path.is_absolute() or any(p in (".", "..") for p in path.parts):
                raise LibraryError("unsafe_location")
            parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
            self.fds.append(parent)
            for component in path.parts[1:-1]:
                parent = os.open(
                    component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
                self.fds.append(parent)
            self.parent = parent
            flags = os.O_RDWR if create else os.O_RDONLY
            if create:
                flags |= os.O_CREAT | os.O_EXCL
            self.fd = os.open(
                path.name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent
            )
            self.fds.append(self.fd)
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise LibraryError("unsafe_location")
            self.identity = _identity(info)
            self.check()
        except Exception:
            self.close()
            raise

    def check(self) -> None:
        # Rewalk without following links: retained parent alone would hide renames.
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in self.path.parts[1:-1]:
                child = os.open(
                    component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
                os.close(parent)
                parent = child
            if _identity(os.fstat(parent)) != _identity(os.fstat(self.parent)):
                raise LibraryError("unsafe_location")
            info = os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
            if _identity(info) != self.identity or info.st_nlink != 1:
                raise LibraryError("unsafe_location")
            for suffix in ("-journal", "-wal", "-shm"):
                try:
                    auxiliary = os.stat(
                        self.path.name + suffix, dir_fd=parent, follow_symlinks=False
                    )
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(auxiliary.st_mode) or auxiliary.st_nlink != 1:
                    raise LibraryError("unsafe_location")
                # Recovery/WAL admission needs its own proven auxiliary-file policy.
                raise LibraryError("busy")
        finally:
            os.close(parent)

    def connection(self, mode: str) -> sqlite3.Connection:
        self.check()
        if mode == "rw" and (
            not os.access(
                self.path.name,
                os.R_OK | os.W_OK,
                dir_fd=self.parent,
                effective_ids=True,
                follow_symlinks=False,
            )
            or not os.access(".", os.W_OK | os.X_OK, dir_fd=self.parent, effective_ids=True)
        ):
            raise LibraryError("permission_denied")
        before = {}
        for name in os.listdir("/proc/self/fd"):
            try:
                info = os.fstat(int(name))
            except OSError:
                continue
            before[name] = (_identity(info), info.st_mode)
        connection = connect(self.path.as_uri() + f"?mode={mode}", uri=True, timeout=0.25)
        try:
            # SQLite must own a new fd for precisely the selected regular file.
            witnessed = False
            for name in os.listdir("/proc/self/fd"):
                try:
                    info = os.stat(f"/proc/self/fd/{name}")
                except FileNotFoundError:
                    continue
                is_new = before.get(name) != (_identity(info), info.st_mode)
                witnessed |= (
                    is_new and stat.S_ISREG(info.st_mode) and _identity(info) == self.identity
                )
            if not witnessed:
                raise LibraryError("unsafe_location")
            self.check()
            if mode == "ro":
                connection.execute("PRAGMA query_only = ON")
            return connection
        except Exception:
            connection.close()
            raise

    def close(self) -> None:
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()


class LibrarySession:
    """One active library; candidates can be prepared before closing an old session.

    Paths are privileged Python input, never an IPC/renderer contract. A session owns
    its query connection and short-lived command connections; no shared threads.
    """

    def __init__(self, selection: _Selection, query: sqlite3.Connection):
        self._selection = selection
        self._query = query
        self._owner = threading.get_ident()
        self._closed = False
        self._command_active = False
        self.descriptor = SessionDescriptor(str(uuid.uuid4()), selection.path.name)

    @classmethod
    def create(cls, path: Path, *, known_media_roots: tuple[Path, ...] = ()) -> LibrarySession:
        cls._check_known_roots(path, known_media_roots)
        return cls._activate(path, create=True)

    @classmethod
    def open(cls, path: Path, *, known_media_roots: tuple[Path, ...] = ()) -> LibrarySession:
        cls._check_known_roots(path, known_media_roots)
        return cls._activate(path, create=False)

    @staticmethod
    def _check_known_roots(path: Path, roots: tuple[Path, ...]) -> None:
        for root in roots:
            if not root.is_absolute() or ".." in root.parts or path.is_relative_to(root):
                raise LibraryError("unsafe_location")

    @classmethod
    def _activate(cls, path: Path, *, create: bool) -> LibrarySession:
        selection = None
        query = None
        try:
            if sqlite3.sqlite_version_info < (3, 37, 0):
                raise LibraryError("incompatible")
            selection = _Selection(path, create=create)
            if create:
                bootstrap = selection.connection("rw")
                try:
                    apply_migrations(bootstrap)
                finally:
                    bootstrap.close()
            query = selection.connection("ro")
            validate_database(query)
            # Reject known roots containing the catalog, without touching those roots.
            for row in query.execute("SELECT normalized_path FROM library_root"):
                root = Path(row[0])
                if not root.is_absolute() or ".." in root.parts:
                    raise LibraryError("unsafe_location")
                if path.is_relative_to(root):
                    raise LibraryError("unsafe_location")
            writable = selection.connection("rw")
            try:
                writable.execute("BEGIN IMMEDIATE")
                writable.rollback()
            finally:
                writable.close()
            return cls(selection, query)
        except Exception as error:
            if query is not None:
                query.close()
            if selection is not None:
                selection.close()
            # Keep failed new artifacts: pathname ownership alone cannot justify unlink.
            raise _translate(error) from None

    def _require_active(self) -> None:
        if self._owner != threading.get_ident():
            raise LibraryError("invalid_request")
        if self._closed:
            raise LibraryError("stale_session")

    @property
    def query_connection(self) -> sqlite3.Connection:
        self._require_active()
        try:
            self._selection.check()
        except Exception as error:
            raise _translate(error) from None
        return self._query

    @contextmanager
    def command_connection(self) -> Iterator[sqlite3.Connection]:
        """Own a distinct rw connection; existing Catalog cases own transactions.

        No implicit retry. Roll back unfinished work and close even on failure.
        """
        self._require_active()
        if self._command_active:
            raise LibraryError("busy")
        connection = None
        self._command_active = True
        try:
            connection = self._selection.connection("rw")
            validate_database(connection)
            yield connection
        except (sqlite3.Error, OSError, IncompatibleSchemaError, LibraryError) as error:
            raise _translate(error) from None
        finally:
            if connection is not None:
                connection.close()
            self._command_active = False

    def close(self) -> None:
        if self._owner != threading.get_ident():
            raise LibraryError("invalid_request")
        if self._command_active:
            raise LibraryError("busy")
        if not self._closed:
            self._query.close()
            self._selection.close()
            self._closed = True

    def __enter__(self) -> LibrarySession:
        self._require_active()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class LibraryLifecycle:
    """Synchronous single-session owner; shell dialogs/preferences belong to D04-01B."""

    def __init__(self) -> None:
        self._active: LibrarySession | None = None
        self.generation = 0

    @property
    def active(self) -> LibrarySession | None:
        return self._active

    def open(self, path: Path, *, known_media_roots: tuple[Path, ...] = ()) -> SessionDescriptor:
        candidate = LibrarySession.open(path, known_media_roots=known_media_roots)
        return self._replace(candidate)

    def create(self, path: Path, *, known_media_roots: tuple[Path, ...] = ()) -> SessionDescriptor:
        candidate = LibrarySession.create(path, known_media_roots=known_media_roots)
        return self._replace(candidate)

    def _replace(self, candidate: LibrarySession) -> SessionDescriptor:
        try:
            self.close()
        except Exception:
            candidate.close()
            raise
        self._active = candidate
        self.generation += 1
        return candidate.descriptor

    def close(self) -> None:
        if self._active is not None:
            self._active.close()
            self._active = None
            self.generation += 1
