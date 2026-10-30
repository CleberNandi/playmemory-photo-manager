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


class HostPlatform(StrEnum):
    POSIX = "posix"
    WINDOWS = "windows"
    OTHER = "other"


class ConfinementKind(StrEnum):
    DESCRIPTOR_RELATIVE = "descriptor_relative"
    PATH_BASED = "path_based"


@dataclass(frozen=True, slots=True)
class ScanLimits:
    """Enumeration budgets; exhaustion raises instead of publishing partial coverage."""

    max_entries: int = 2000
    max_depth: int = 32

    def __post_init__(self) -> None:
        for value in (self.max_entries, self.max_depth):
            if type(value) is not int or value < 0:
                raise ValueError("scan limits must be non-negative integers")


class ScanResourceLimitError(RuntimeError):
    """No ScanResult is published on exhaustion; diagnostics never contain paths."""

    def __init__(self, reason: str, observed_count: int, depth: int):
        self.reason = reason
        self.observed_count = observed_count
        self.depth = depth
        super().__init__("resource_limit")


@dataclass(frozen=True, slots=True)
class ScanOptions:
    """Options deliberately limited to safe observation behavior."""

    recursive: bool = True
    cancellation_requested: Callable[[], bool] | None = field(
        default=None, repr=False, compare=False
    )
    limits: ScanLimits | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.recursive, bool):
            raise TypeError("recursive must be boolean")
        if self.cancellation_requested is not None and not callable(self.cancellation_requested):
            raise TypeError("cancellation_requested must be callable or None")
        if self.limits is not None and not isinstance(self.limits, ScanLimits):
            raise TypeError("limits must be ScanLimits or None")


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
class ScanEnvironment:
    platform: HostPlatform
    confinement: ConfinementKind


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
    environment: ScanEnvironment | None = None

    @property
    def is_complete(self) -> bool:
        return self.status is ScanStatus.COMPLETE
