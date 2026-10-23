"""Immutable contracts for read-only filesystem observations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ScanStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    ROOT_UNAVAILABLE = "root_unavailable"
    FAILED = "failed"


class EntryType(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    REPARSE_POINT = "reparse_point"
    OTHER = "other"


class EvidenceKind(StrEnum):
    DIRECT_OBSERVATION = "direct_observation"
    UNCONFIRMED_INFERENCE = "unconfirmed_inference"


class FailureKind(StrEnum):
    PERMISSION_DENIED = "permission_denied"
    DISAPPEARED = "disappeared"
    NOT_DIRECTORY = "not_directory"
    SYMLINK_ROOT = "symlink_root"
    REPARSE_ROOT = "reparse_root"
    IO_ERROR = "io_error"


class FailureOperation(StrEnum):
    OBSERVE_ROOT = "observe_root"
    ENUMERATE_DIRECTORY = "enumerate_directory"
    OBSERVE_ENTRY = "observe_entry"


@dataclass(frozen=True, slots=True)
class ScanOptions:
    """Options deliberately limited to safe observation behavior."""

    recursive: bool = True
    cancellation_requested: Callable[[], bool] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.recursive, bool):
            raise TypeError("recursive must be boolean")
        if self.cancellation_requested is not None and not callable(self.cancellation_requested):
            raise TypeError("cancellation_requested must be callable or None")


@dataclass(frozen=True, slots=True)
class ScanScope:
    relative_path: str
    recursive: bool
    follows_links: bool


@dataclass(frozen=True, slots=True)
class PhysicalIdentity:
    """Point-in-time values reported by the host, not a permanent identity."""

    device: int
    file_id: int


@dataclass(frozen=True, slots=True)
class ObservedTimestamps:
    """Raw filesystem timestamps; exact semantics remain platform-dependent."""

    modified_ns: int | None
    accessed_ns: int | None
    changed_ns: int | None


@dataclass(frozen=True, slots=True)
class RootObservation:
    requested_path: str
    absolute_path: str
    physical_identity: PhysicalIdentity | None


@dataclass(frozen=True, slots=True)
class EntryObservation:
    relative_path: str
    entry_type: EntryType
    byte_size: int | None
    timestamps: ObservedTimestamps
    physical_identity: PhysicalIdentity | None
    evidence_kind: EvidenceKind = EvidenceKind.DIRECT_OBSERVATION


@dataclass(frozen=True, slots=True)
class ObservationFailure:
    relative_path: str | None
    operation: FailureOperation
    kind: FailureKind
    compromises_coverage: bool
    error_code: int | None


@dataclass(frozen=True, slots=True)
class ScanResult:
    run_id: str
    root: RootObservation | None
    scope: ScanScope
    started_at: datetime
    finished_at: datetime
    status: ScanStatus
    covered_directories: tuple[str, ...]
    entries: tuple[EntryObservation, ...]
    failures: tuple[ObservationFailure, ...]

    @property
    def is_complete(self) -> bool:
        return self.status is ScanStatus.COMPLETE
