"""Immutable results for read-only exact-duplicate detection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DuplicateCoverage(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class DuplicateIssueKind(StrEnum):
    ROOT_OFFLINE = "root_offline"
    LOCATION_UNAVAILABLE = "location_unavailable"
    SYMLINK_BLOCKED = "symlink_blocked"
    INVALID_PATH = "invalid_path"
    NOT_REGULAR_FILE = "not_regular_file"
    FILE_CHANGED = "file_changed"
    READ_FAILED = "read_failed"
    CONFINEMENT_UNAVAILABLE = "confinement_unavailable"


@dataclass(frozen=True, slots=True)
class DuplicateIssue:
    kind: DuplicateIssueKind
    asset_id: str
    location_id: str
    library_root_id: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class DuplicateMember:
    asset_id: str
    location_id: str
    library_root_id: str
    relative_path: str
    byte_size: int
    sha256: str
    device: int
    file_id: int
    link_count: int

    @property
    def physical_identity(self) -> tuple[int, int]:
        return (self.device, self.file_id)

    @property
    def is_hardlinked(self) -> bool:
        return self.link_count > 1


@dataclass(frozen=True, slots=True)
class ExactDuplicateGroup:
    sha256: str
    byte_size: int
    members: tuple[DuplicateMember, ...]
    physical_copy_count: int


@dataclass(frozen=True, slots=True)
class ExactDuplicateResult:
    coverage: DuplicateCoverage
    groups: tuple[ExactDuplicateGroup, ...]
    issues: tuple[DuplicateIssue, ...]
    eligible_location_count: int
    hashed_location_count: int


class DuplicateDecisionStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"


class DuplicatePlanState(StrEnum):
    PENDING = "pending"
    READY = "ready"
    BLOCKED = "blocked"
    STALE = "stale"


class DuplicateBlockKind(StrEnum):
    INCOMPLETE_COVERAGE = "incomplete_coverage"
    HARDLINK = "hardlink"
    IDENTITY_CONFLICT = "identity_conflict"
    PROTECTED = "protected"
    PRESERVED_COPY_UNVERIFIED = "preserved_copy_unverified"


@dataclass(frozen=True, slots=True)
class ExactDuplicateDecision:
    id: str
    sha256: str
    byte_size: int
    keep_location_id: str
    reason: str
    evidence_fingerprint: str
    status: DuplicateDecisionStatus
    members: tuple[DuplicateMember, ...]


@dataclass(frozen=True, slots=True)
class DuplicatePlanMember:
    member: DuplicateMember
    keep: bool
    candidate: bool
    protected: bool
    hardlinked: bool


@dataclass(frozen=True, slots=True)
class DuplicatePlanGroup:
    sha256: str
    byte_size: int
    state: DuplicatePlanState
    decision_id: str | None
    reason: str | None
    members: tuple[DuplicatePlanMember, ...]
    blocks: tuple[DuplicateBlockKind, ...]


@dataclass(frozen=True, slots=True)
class ExactDuplicatePlan:
    groups: tuple[DuplicatePlanGroup, ...]
    coverage: DuplicateCoverage
    issues: tuple[DuplicateIssue, ...]
    action_authorized: bool = False
    operations_performed: bool = False
