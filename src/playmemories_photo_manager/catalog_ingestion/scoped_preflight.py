"""Read-only physical preflight for an exact authorized batch, outside SQLite."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from ..scanner import PhysicalIdentity
from .media import (
    MediaVerificationCancelled,
    _Changed,
    _Directories,
    _identity,
    _mount_id,
    _verify_file,
)
from .scoped_authorization import ScopedIngestionAuthorization, validate_scoped_authorization
from .scoping import ScopedIngestionProposal

MAX_HELD_DIRECTORIES = 128


class ScopedPreflightError(RuntimeError):
    """Fixed public reason; no source paths or operating-system error details."""


def _open_root(path: Path, identity: PhysicalIdentity, mount: int) -> tuple[_Directories, int]:
    directories = _Directories()
    try:
        if not path.is_absolute() or ".." in path.parts:
            raise ScopedPreflightError("source_changed")
        root_fd = directories.start()
        for component in path.parts[1:]:
            if len(directories.fds) >= MAX_HELD_DIRECTORIES:
                raise ScopedPreflightError("resource_limit")
            root_fd = directories.child(root_fd, component)
        directories.check()
        if _identity(os.fstat(root_fd)) != identity or _mount_id(root_fd) != mount:
            raise ScopedPreflightError("source_changed")
        return directories, root_fd
    except BaseException:
        directories.close()
        raise


class ScopedPreflight:
    """Ephemeral held root; check_root must run again at the transaction boundary.

    This is not a durable capability or a filesystem snapshot. No file descriptor
    or proof object is sent to the renderer or persisted in the catalog.
    """

    def __init__(self, path, identity, mount, directories, root_fd, authorization):
        self._path = path
        self._identity = identity
        self._mount = mount
        self._directories = directories
        self._root_fd = root_fd
        self.authorization = authorization
        self._closed = False
        self.captures = {}

    def check_root(self) -> None:
        if self._closed:
            raise ScopedPreflightError("preflight_closed")
        try:
            self._directories.check()
            if (
                _identity(os.fstat(self._root_fd)) != self._identity
                or _mount_id(self._root_fd) != self._mount
            ):
                raise ScopedPreflightError("source_changed")
            # A retained descriptor alone cannot detect a new bind mount at the same path.
            fresh, _ = _open_root(self._path, self._identity, self._mount)
            fresh.close()
        except (OSError, _Changed):
            raise ScopedPreflightError("source_changed") from None

    def _close(self):
        self._closed = True
        self._directories.close()


@contextmanager
def preflight_scoped_ingestion(
    scoped: ScopedIngestionProposal,
    authorization: ScopedIngestionAuthorization,
    *,
    expected_root_mount: int,
    cancellation_requested: Callable[[], bool] | None = None,
) -> Iterator[ScopedPreflight]:
    """Reverify only selected JPEGs against preparation evidence; never write.

    Mount identity must come from the private preparation binding, never the UI
    or a freshly inferred value. Use in a supervised worker: cooperative deadlines
    do not interrupt blocked kernel I/O or provide an RSS/process lifetime ceiling.
    """
    validate_scoped_authorization(scoped, authorization)
    if sys.platform != "linux":
        raise ScopedPreflightError("unsupported_platform")
    if type(expected_root_mount) is not int or expected_root_mount <= 0:
        raise ScopedPreflightError("invalid_mount_binding")
    scan = scoped.original.scan_result
    path = Path(scan.root.absolute_path)
    identity = scan.root.physical_identity
    directories = None
    held = None
    deadline = time.monotonic() + 30
    file_deadline = deadline

    def checkpoint():
        if cancellation_requested is not None and cancellation_requested():
            raise MediaVerificationCancelled
        if time.monotonic() >= min(deadline, file_deadline):
            raise ScopedPreflightError("verification_timeout")

    try:
        checkpoint()
        directories, root_fd = _open_root(path, identity, expected_root_mount)
        held = ScopedPreflight(
            path, identity, expected_root_mount, directories, root_fd, authorization
        )
        by_id = {item.candidate_id: item for item in scoped.eligibilities}
        for identifier in authorization.candidate_ids:
            file_deadline = min(deadline, time.monotonic() + 1)
            checkpoint()
            item = by_id[identifier]
            reason, detected, fingerprint = _verify_file(
                root_fd,
                expected_root_mount,
                item.observation,
                checkpoint,
                lambda values, path=item.candidate.relative_path: held.captures.__setitem__(
                    path, values
                ),
            )
            if (
                reason != item.reason
                or detected != item.detected_format
                or fingerprint != item.fingerprint
            ):
                raise ScopedPreflightError("source_changed")
            checkpoint()
            held.check_root()
        checkpoint()
        held.check_root()
    except (OSError, _Changed):
        if held is not None:
            held._close()
        elif directories is not None:
            directories.close()
        raise ScopedPreflightError("source_changed") from None
    except BaseException:
        if held is not None:
            held._close()
        elif directories is not None:
            directories.close()
        raise
    try:
        yield held
    finally:
        held._close()
