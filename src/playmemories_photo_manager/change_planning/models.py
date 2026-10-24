"""Immutable contracts for conservative catalog change planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from playmemories_photo_manager.catalog import Asset, FileLocation, LibraryRoot
from playmemories_photo_manager.scanner import EntryObservation, PhysicalIdentity, ScanScope


class ChangeClassification(StrEnum):
    KNOWN_LOCATION_OBSERVED = "known_location_observed"
    NEW_FILE_CANDIDATE = "new_file_candidate"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"


class PlanStatus(StrEnum):
    READY = "ready"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"


class DiagnosticSeverity(StrEnum):
    INFORMATION = "information"
    WARNING = "warning"
    ERROR = "error"


class DiagnosticCode(StrEnum):
    INVALID_ASSESSMENT = "invalid_assessment"
    INVALID_SNAPSHOT = "invalid_snapshot"
    INVALID_CONTEXT = "invalid_context"
    ROOT_ID_MISMATCH = "root_id_mismatch"
    ROOT_PATH_MISMATCH = "root_path_mismatch"
    ROOT_IDENTITY_MISMATCH = "root_identity_mismatch"
    ROOT_IDENTITY_UNAVAILABLE = "root_identity_unavailable"
    SCOPE_MISMATCH = "scope_mismatch"
    INCOMPLETE_COVERAGE = "incomplete_coverage"
    ROOT_UNAVAILABLE = "root_unavailable"
    PATH_COLLISION = "path_collision"
    ACTIVE_LOCATION_CONFLICT = "active_location_conflict"
    PHYSICAL_IDENTITY_CONTRADICTION = "physical_identity_contradiction"
    PHYSICAL_IDENTITY_UNAVAILABLE = "physical_identity_unavailable"
    PREVIOUSLY_MISSING_PATH = "previously_missing_path"
    NON_FILE_OBSERVATION = "non_file_observation"
    INCONCLUSIVE_EVIDENCE = "inconclusive_evidence"
    ABSENCE_NOT_AUTHORIZED = "absence_not_authorized"
    CONTENT_NOT_VERIFIED = "content_not_verified"
    READ_VERSION_UNAVAILABLE = "read_version_unavailable"


@dataclass(frozen=True, slots=True)
class LocationPhysicalEvidence:
    location_id: str
    identity: PhysicalIdentity


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """Caller-built, bounded logical read of one catalog root and scope."""

    library_root: LibraryRoot
    assets: tuple[Asset, ...]
    locations: tuple[FileLocation, ...]
    physical_evidence: tuple[LocationPhysicalEvidence, ...]
    effective_scope: ScanScope
    read_version: str | None = None


@dataclass(frozen=True, slots=True)
class PlanningContext:
    """Explicit binding between the catalog root and the observed root."""

    library_root_id: str
    catalog_root_path: str
    observed_root_path: str
    scope: ScanScope
    catalog_root_identity: PhysicalIdentity | None = None


@dataclass(frozen=True, slots=True)
class PlanDiagnostic:
    code: DiagnosticCode
    severity: DiagnosticSeverity
    relative_path: str | None = None
    location_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlannedChange:
    classification: ChangeClassification
    relative_path: str
    observation: EntryObservation
    asset_id: str | None = None
    location_id: str | None = None
    diagnostics: tuple[PlanDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogChangePlan:
    run_id: str
    library_root_id: str
    scope: ScanScope
    snapshot_read_version: str | None
    status: PlanStatus
    changes: tuple[PlannedChange, ...]
    diagnostics: tuple[PlanDiagnostic, ...]
    permits_absence_conclusions: bool = field(default=False, init=False)
    authorizes_catalog_mutation: bool = field(default=False, init=False)
