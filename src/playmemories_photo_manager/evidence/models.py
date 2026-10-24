"""Immutable contracts for evaluating filesystem observation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from playmemories_photo_manager.scanner import (
    EntryObservation,
    ObservationFailure,
    PhysicalIdentity,
    RootObservation,
    ScanScope,
    ScanStatus,
)


class CoverageClassification(StrEnum):
    COMPLETE_RECURSIVE_SCOPE = "complete_recursive_scope"
    COMPLETE_NON_RECURSIVE_SCOPE = "complete_non_recursive_scope"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    ROOT_UNAVAILABLE = "root_unavailable"
    FAILED = "failed"
    INVALID = "invalid"


class StructuralValidation(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class ReasonSeverity(StrEnum):
    INFORMATION = "information"
    ERROR = "error"


class ReasonCode(StrEnum):
    INVALID_CONTRACT_TYPE = "invalid_contract_type"
    INVALID_RUN_ID = "invalid_run_id"
    INVALID_TIME_RANGE = "invalid_time_range"
    TIMESTAMPS_NOT_UTC = "timestamps_not_utc"
    ROOT_REQUIRED = "root_required"
    UNAVAILABLE_ROOT_HAS_OBSERVATIONS = "unavailable_root_has_observations"
    INVALID_SCOPE_PATH = "invalid_scope_path"
    LINKS_FOLLOWED = "links_followed"
    INVALID_ENTRY_PATH = "invalid_entry_path"
    INVALID_FAILURE_PATH = "invalid_failure_path"
    INVALID_COVERED_DIRECTORY = "invalid_covered_directory"
    DUPLICATE_ENTRY_PATH = "duplicate_entry_path"
    DUPLICATE_COVERED_DIRECTORY = "duplicate_covered_directory"
    COVERED_DIRECTORY_NOT_OBSERVED = "covered_directory_not_observed"
    DIRECTORY_NOT_COVERED = "directory_not_covered"
    COMPLETE_HAS_FAILURES = "complete_has_failures"
    COMPLETE_HAS_NON_DIRECT_EVIDENCE = "complete_has_non_direct_evidence"
    COMPLETE_ROOT_NOT_COVERED = "complete_root_not_covered"
    PARTIAL_WITHOUT_COVERAGE_FAILURE = "partial_without_coverage_failure"
    ROOT_FAILURE_REQUIRED = "root_failure_required"
    FAILED_HAS_OBSERVATIONS = "failed_has_observations"
    FILE_SIZE_MISSING = "file_size_missing"
    NON_FILE_HAS_SIZE = "non_file_has_size"
    INVALID_BYTE_SIZE = "invalid_byte_size"
    INVALID_PHYSICAL_IDENTITY = "invalid_physical_identity"
    INVALID_TIMESTAMP = "invalid_timestamp"
    PATH_OUTSIDE_SCOPE = "path_outside_scope"
    ENTRY_PARENT_NOT_OBSERVED = "entry_parent_not_observed"
    PHYSICAL_IDENTITY_CONTRADICTION = "physical_identity_contradiction"
    INVALID_ENVIRONMENT = "invalid_environment"
    UNCONFIRMED_INFERENCE = "unconfirmed_inference"
    POTENTIAL_HARDLINK = "potential_hardlink"
    NON_RECURSIVE_SCOPE = "non_recursive_scope"
    ENUMERATION_NOT_SNAPSHOT = "enumeration_not_snapshot"
    FILESYSTEM_TIMESTAMPS_NOT_CAPTURE_TIME = "filesystem_timestamps_not_capture_time"
    PHYSICAL_IDENTITY_NOT_LOGICAL_IDENTITY = "physical_identity_not_logical_identity"
    CONTENT_NOT_VERIFIED = "content_not_verified"
    ROOT_UNAVAILABLE_PROVES_NO_ABSENCE = "root_unavailable_proves_no_absence"
    PLATFORM_PROVENANCE_MISSING = "platform_provenance_missing"
    PATH_BASED_CONFINEMENT = "path_based_confinement"
    POSIX_CONFINEMENT_NOT_ATOMIC = "posix_confinement_not_atomic"


class InferenceKind(StrEnum):
    POTENTIAL_HARDLINK = "potential_hardlink"


class PortabilityLimitation(StrEnum):
    PLATFORM_OR_CONFINEMENT_UNRECORDED = "platform_or_confinement_unrecorded"
    PATH_BASED_CONFINEMENT_NOT_RACE_SAFE = "path_based_confinement_not_race_safe"
    PHYSICAL_IDENTITY_IS_HOST_SCOPED = "physical_identity_is_host_scoped"
    FILESYSTEM_PATH_SEMANTICS_ARE_HOST_DEFINED = "filesystem_path_semantics_are_host_defined"


class DecisionImpediment(StrEnum):
    STRUCTURALLY_INVALID = "structurally_invalid"
    INCOMPLETE_COVERAGE = "incomplete_coverage"
    NON_RECURSIVE_SCOPE = "non_recursive_scope"
    ROOT_UNAVAILABLE = "root_unavailable"
    ENUMERATION_NOT_ATOMIC = "enumeration_not_atomic"
    CONTENT_NOT_VERIFIED = "content_not_verified"
    LOGICAL_IDENTITY_UNCONFIRMED = "logical_identity_unconfirmed"
    CONFINEMENT_NOT_DEMONSTRATED = "confinement_not_demonstrated"


@dataclass(frozen=True, slots=True)
class AssessmentReason:
    code: ReasonCode
    severity: ReasonSeverity
    relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceInference:
    kind: InferenceKind
    relative_paths: tuple[str, ...]
    physical_identity: PhysicalIdentity


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    run_id: str
    original_status: ScanStatus
    root: RootObservation | None
    scope: ScanScope
    coverage: CoverageClassification
    structural_validation: StructuralValidation
    accepted_entries: tuple[EntryObservation, ...]
    inconclusive_entries: tuple[EntryObservation, ...]
    failures: tuple[ObservationFailure, ...]
    inferences: tuple[EvidenceInference, ...]
    reasons: tuple[AssessmentReason, ...]
    portability_limitations: tuple[PortabilityLimitation, ...]
    decision_impediments: tuple[DecisionImpediment, ...]
