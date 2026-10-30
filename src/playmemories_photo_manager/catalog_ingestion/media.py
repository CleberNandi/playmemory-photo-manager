"""Trusted Linux media eligibility; no grants, database writes, or renderer input.

Only use inside the future disposable preparation worker. Cooperative checkpoints
do not interrupt kernel I/O or impose an RSS ceiling on the current process.
"""

from __future__ import annotations

import os
import stat
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from ..evidence import CoverageClassification, StructuralValidation, evaluate
from ..scanner import (
    ConfinementKind,
    EntryObservation,
    EntryType,
    HostPlatform,
    PhysicalIdentity,
    ScanResult,
    ScanStatus,
)
from .jpeg import PROFILE, inspect_jpeg
from .models import CandidateReference

EXCLUDED_REASONS = frozenset(
    {
        "unsupported_extension",
        "not_regular_file",
        "empty_file",
        "byte_limit_exceeded",
        "invalid_jpeg_signature",
        "truncated_jpeg",
        "malformed_jpeg_segment",
        "unsupported_jpeg_frame",
        "dimension_limit_exceeded",
        "segment_limit_exceeded",
    }
)
FAILED_REASONS = frozenset(
    {
        "entry_changed_during_verification",
        "read_failed",
        "verification_timeout",
    }
)


class MediaPreparationError(RuntimeError):
    """Sanitized failure of the whole preparation's physical boundary."""


class MediaVerificationCancelled(Exception):
    pass


class _VerificationTimeout(Exception):
    pass


class _Changed(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PhysicalFingerprint:
    root: PhysicalIdentity
    before: tuple[int, int, int, int, int]
    after: tuple[int, int, int, int, int]


@dataclass(frozen=True, slots=True)
class MediaEligibility:
    candidate_id: str
    candidate: CandidateReference
    observation: EntryObservation
    state: str
    reason: str
    detected_format: str | None
    fingerprint: PhysicalFingerprint | None
    profile: str = PROFILE
    decoding: str = "not_checked"


def _identity(info):
    return PhysicalIdentity(info.st_dev, info.st_ino)


def _file_state(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _mount_id(fd: int) -> int:
    # st_dev alone cannot distinguish bind mounts of the same filesystem.
    with open(f"/proc/self/fdinfo/{fd}", encoding="ascii") as source:
        for line in source:
            if line.startswith("mnt_id:"):
                return int(line.split(":", 1)[1])
    raise OSError("mount identity unavailable")


class _Directories:
    def __init__(self):
        self.fds = []
        self.links = []

    def start(self):
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.fds.append(fd)
        return fd

    def child(self, parent: int, name: str, mount: int | None = None):
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        self.fds.append(fd)
        identity = _identity(os.fstat(fd))
        self.links.append((parent, name, identity))
        if mount is not None and _mount_id(fd) != mount:
            raise _Changed
        return fd

    def check(self):
        for parent, name, identity in self.links:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or _identity(info) != identity:
                raise _Changed

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()


def _verify_file(root_fd, mount, observation, checkpoint):
    parents = _Directories()
    reason, detected, fingerprint = "read_failed", None, None
    try:
        parent = root_fd
        parts = PurePosixPath(observation.relative_path).parts
        for component in parts[:-1]:
            checkpoint()
            parent = parents.child(parent, component, mount)
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(file_fd, "rb", buffering=0) as source:
            info = os.fstat(source.fileno())
            before = _file_state(info)
            expected = (
                observation.physical_identity.device,
                observation.physical_identity.file_id,
                observation.byte_size,
                observation.timestamps.modified_ns,
                observation.timestamps.changed_ns,
            )
            if not stat.S_ISREG(info.st_mode) or before != expected:
                raise _Changed
            if _mount_id(source.fileno()) != mount:
                raise _Changed
            try:
                result = inspect_jpeg(source, info.st_size, checkpoint=checkpoint)
                reason, detected = result.reason, result.detected_format
            except _VerificationTimeout:
                reason = "verification_timeout"
            except OSError:
                reason = "read_failed"
            finally:
                after = _file_state(os.fstat(source.fileno()))
                linked = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                if (
                    before != after
                    or not stat.S_ISREG(linked.st_mode)
                    or _file_state(linked) != after
                ):
                    raise _Changed
                parents.check()
            fingerprint = PhysicalFingerprint(_identity(os.fstat(root_fd)), before, after)
    except _Changed:
        reason = "entry_changed_during_verification"
    except _VerificationTimeout:
        reason = "verification_timeout"
    except OSError:
        reason = "read_failed"
    finally:
        parents.close()
    return reason, detected, fingerprint


def _check_excluded_entry(root_fd, mount, observation):
    """O_PATH checks identity/mount without reading even FIFO/symlink contents."""
    parents = _Directories()
    try:
        parent = root_fd
        parts = PurePosixPath(observation.relative_path).parts
        for component in parts[:-1]:
            parent = parents.child(parent, component, mount)
        fd = os.open(parts[-1], os.O_PATH | os.O_NOFOLLOW, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if _identity(info) != observation.physical_identity or _mount_id(fd) != mount:
                raise _Changed
            expected_type = observation.entry_type
            if (
                expected_type is EntryType.DIRECTORY
                and not stat.S_ISDIR(info.st_mode)
                or expected_type is EntryType.FILE
                and not stat.S_ISREG(info.st_mode)
                or expected_type is EntryType.SYMLINK
                and not stat.S_ISLNK(info.st_mode)
                or info.st_mtime_ns != observation.timestamps.modified_ns
                or info.st_ctime_ns != observation.timestamps.changed_ns
            ):
                raise _Changed
            linked = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if _identity(linked) != _identity(info):
                raise _Changed
            parents.check()
        finally:
            os.close(fd)
    finally:
        parents.close()


def classify_media(
    scan_result: ScanResult,
    root_id: str,
    *,
    cancellation_requested: Callable[[], bool] | None = None,
) -> tuple[MediaEligibility, ...]:
    """Classify a complete bounded scan, without claiming a current filesystem snapshot.

    Paths and physical identity come from trusted scanner evidence, never the UI.
    Nonregular/unsupported-extension entries are excluded without opening contents.
    Physical failures remain failed records; the scoped validator rejects the batch.
    """
    if str(UUID(root_id)) != root_id:
        raise ValueError("invalid root identifier")
    assessment = evaluate(scan_result)
    if (
        sys.platform != "linux"
        or assessment.structural_validation is not StructuralValidation.VALID
        or assessment.coverage is not CoverageClassification.COMPLETE_RECURSIVE_SCOPE
        or scan_result.status is not ScanStatus.COMPLETE
        or scan_result.root is None
        or scan_result.root.physical_identity is None
        or scan_result.environment is None
        or scan_result.environment.platform is not HostPlatform.POSIX
        or scan_result.environment.confinement is not ConfinementKind.DESCRIPTOR_RELATIVE
        or len(scan_result.entries) > 2000
        or any(len(PurePosixPath(e.relative_path).parts) > 32 for e in scan_result.entries)
    ):
        raise MediaPreparationError("invalid_preparation")
    directories = _Directories()
    batch_deadline = time.monotonic() + 30
    file_deadline = batch_deadline

    def checkpoint():
        if cancellation_requested is not None and cancellation_requested():
            raise MediaVerificationCancelled
        if time.monotonic() >= min(file_deadline, batch_deadline):
            raise _VerificationTimeout

    try:
        path = Path(scan_result.root.absolute_path)
        if not path.is_absolute() or ".." in path.parts:
            raise _Changed
        root_fd = directories.start()
        for component in path.parts[1:]:
            root_fd = directories.child(root_fd, component)
        if _identity(os.fstat(root_fd)) != scan_result.root.physical_identity:
            raise _Changed
        mount = _mount_id(root_fd)
        results = []
        for observation in scan_result.entries:
            file_deadline = min(time.monotonic() + 1, batch_deadline)
            checkpoint()
            if observation.entry_type is not EntryType.FILE:
                _check_excluded_entry(root_fd, mount, observation)
                reason, detected, fingerprint = "not_regular_file", None, None
            elif PurePosixPath(observation.relative_path).suffix.lower() not in (".jpg", ".jpeg"):
                _check_excluded_entry(root_fd, mount, observation)
                reason, detected, fingerprint = "unsupported_extension", None, None
            elif observation.physical_identity is None:
                reason, detected, fingerprint = "entry_changed_during_verification", None, None
            else:
                reason, detected, fingerprint = _verify_file(
                    root_fd, mount, observation, checkpoint
                )
            directories.check()
            if _identity(os.fstat(root_fd)) != scan_result.root.physical_identity:
                raise _Changed
            results.append(
                MediaEligibility(
                    str(uuid4()),
                    CandidateReference(scan_result.run_id, root_id, observation.relative_path),
                    observation,
                    "eligible"
                    if reason == "eligible_jpeg"
                    else "failed"
                    if reason in FAILED_REASONS
                    else "excluded",
                    reason,
                    detected,
                    fingerprint,
                )
            )
        directories.check()
        checkpoint()
        return tuple(results)
    except (_Changed, OSError):
        raise MediaPreparationError("root_changed") from None
    except _VerificationTimeout:
        raise MediaPreparationError("verification_timeout") from None
    finally:
        directories.close()
