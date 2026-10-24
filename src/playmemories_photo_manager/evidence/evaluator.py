"""Pure validation and classification of scanner evidence."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC
from pathlib import PurePosixPath

from playmemories_photo_manager.scanner import (
    ConfinementKind,
    EntryObservation,
    EntryType,
    EvidenceKind,
    FailureOperation,
    HostPlatform,
    PhysicalIdentity,
    ScanResult,
    ScanStatus,
)

from .models import (
    AssessmentReason,
    CoverageClassification,
    DecisionImpediment,
    EvidenceAssessment,
    EvidenceInference,
    InferenceKind,
    PortabilityLimitation,
    ReasonCode,
    ReasonSeverity,
    StructuralValidation,
)


def evaluate(scan_result: ScanResult) -> EvidenceAssessment:
    """Evaluate one immutable scan result without consulting external state."""
    if not isinstance(scan_result, ScanResult):
        raise TypeError("scan_result must be ScanResult")

    errors: list[AssessmentReason] = []
    information: list[AssessmentReason] = []
    _validate_identity_and_time(scan_result, errors)
    _validate_paths_and_entries(scan_result, errors)
    _validate_status(scan_result, errors)

    valid = not errors
    validation = StructuralValidation.VALID if valid else StructuralValidation.INVALID
    coverage = _coverage(scan_result, valid)
    direct = tuple(
        entry
        for entry in scan_result.entries
        if entry.evidence_kind is EvidenceKind.DIRECT_OBSERVATION
    )
    inconclusive = tuple(
        entry
        for entry in scan_result.entries
        if entry.evidence_kind is not EvidenceKind.DIRECT_OBSERVATION
    )
    if not valid:
        inconclusive = scan_result.entries
        direct = ()
    elif inconclusive:
        information.append(_reason(ReasonCode.UNCONFIRMED_INFERENCE))

    inferences = _potential_hardlinks(direct)
    for inference in inferences:
        information.append(_reason(ReasonCode.POTENTIAL_HARDLINK, inference.relative_paths[0]))
    if not scan_result.scope.recursive:
        information.append(_reason(ReasonCode.NON_RECURSIVE_SCOPE))
    information.extend(
        (
            _reason(ReasonCode.ENUMERATION_NOT_SNAPSHOT),
            _reason(ReasonCode.CONTENT_NOT_VERIFIED),
            _reason(ReasonCode.PHYSICAL_IDENTITY_NOT_LOGICAL_IDENTITY),
        )
    )
    if direct:
        information.append(_reason(ReasonCode.FILESYSTEM_TIMESTAMPS_NOT_CAPTURE_TIME))
    if scan_result.status is ScanStatus.ROOT_UNAVAILABLE:
        information.append(_reason(ReasonCode.ROOT_UNAVAILABLE_PROVES_NO_ABSENCE))

    portability, portability_reasons = _portability(scan_result)
    information.extend(portability_reasons)
    impediments = _impediments(scan_result, coverage, validation, portability)
    return EvidenceAssessment(
        run_id=scan_result.run_id,
        original_status=scan_result.status,
        coverage=coverage,
        structural_validation=validation,
        accepted_entries=direct,
        inconclusive_entries=inconclusive,
        failures=scan_result.failures,
        inferences=inferences,
        reasons=tuple(errors + information),
        portability_limitations=portability,
        decision_impediments=impediments,
    )


def _validate_identity_and_time(result: ScanResult, errors: list[AssessmentReason]) -> None:
    try:
        identifier = uuid.UUID(result.run_id)
    except (ValueError, AttributeError, TypeError):
        errors.append(_error(ReasonCode.INVALID_RUN_ID))
    else:
        if identifier.version != 4 or str(identifier) != result.run_id:
            errors.append(_error(ReasonCode.INVALID_RUN_ID))
    if (
        result.started_at.tzinfo is None
        or result.finished_at.tzinfo is None
        or result.started_at.utcoffset() != UTC.utcoffset(result.started_at)
        or result.finished_at.utcoffset() != UTC.utcoffset(result.finished_at)
    ):
        errors.append(_error(ReasonCode.TIMESTAMPS_NOT_UTC))
    if result.finished_at < result.started_at:
        errors.append(_error(ReasonCode.INVALID_TIME_RANGE))


def _validate_paths_and_entries(result: ScanResult, errors: list[AssessmentReason]) -> None:
    if not _valid_relative_path(result.scope.relative_path, allow_root=True):
        errors.append(_error(ReasonCode.INVALID_SCOPE_PATH, result.scope.relative_path))
    if result.scope.follows_links:
        errors.append(_error(ReasonCode.LINKS_FOLLOWED))

    entry_paths: set[str] = set()
    directory_paths: set[str] = set()
    for entry in result.entries:
        path = entry.relative_path
        if not _valid_relative_path(path):
            errors.append(_error(ReasonCode.INVALID_ENTRY_PATH, path))
        if path in entry_paths:
            errors.append(_error(ReasonCode.DUPLICATE_ENTRY_PATH, path))
        entry_paths.add(path)
        if entry.entry_type is EntryType.DIRECTORY:
            directory_paths.add(path)
        _validate_entry(entry, errors)

    covered = set(result.covered_directories)
    if len(covered) != len(result.covered_directories):
        errors.append(_error(ReasonCode.DUPLICATE_COVERED_DIRECTORY))
    for path in result.covered_directories:
        if not _valid_relative_path(path, allow_root=True):
            errors.append(_error(ReasonCode.INVALID_COVERED_DIRECTORY, path))
        elif path != "." and path not in directory_paths:
            errors.append(_error(ReasonCode.COVERED_DIRECTORY_NOT_OBSERVED, path))
    if result.status is ScanStatus.COMPLETE and result.scope.recursive:
        for path in sorted(directory_paths - covered):
            errors.append(_error(ReasonCode.DIRECTORY_NOT_COVERED, path))
    for failure in result.failures:
        if failure.relative_path is not None and not _valid_relative_path(
            failure.relative_path, allow_root=True
        ):
            errors.append(_error(ReasonCode.INVALID_FAILURE_PATH, failure.relative_path))


def _validate_entry(entry: EntryObservation, errors: list[AssessmentReason]) -> None:
    if entry.byte_size is not None and (
        isinstance(entry.byte_size, bool)
        or not isinstance(entry.byte_size, int)
        or entry.byte_size < 0
    ):
        errors.append(_error(ReasonCode.INVALID_BYTE_SIZE, entry.relative_path))
    elif entry.entry_type is EntryType.FILE and entry.byte_size is None:
        errors.append(_error(ReasonCode.FILE_SIZE_MISSING, entry.relative_path))
    elif entry.entry_type is not EntryType.FILE and entry.byte_size is not None:
        errors.append(_error(ReasonCode.NON_FILE_HAS_SIZE, entry.relative_path))
    identity = entry.physical_identity
    if identity is not None and (
        isinstance(identity.device, bool)
        or not isinstance(identity.device, int)
        or isinstance(identity.file_id, bool)
        or not isinstance(identity.file_id, int)
        or identity.file_id == 0
    ):
        errors.append(_error(ReasonCode.INVALID_PHYSICAL_IDENTITY, entry.relative_path))


def _validate_status(result: ScanResult, errors: list[AssessmentReason]) -> None:
    if (
        result.status
        in {
            ScanStatus.COMPLETE,
            ScanStatus.PARTIAL,
            ScanStatus.CANCELLED,
            ScanStatus.FAILED,
        }
        and result.root is None
    ):
        errors.append(_error(ReasonCode.ROOT_REQUIRED))
    if result.status is ScanStatus.COMPLETE:
        if result.failures:
            errors.append(_error(ReasonCode.COMPLETE_HAS_FAILURES))
        if "." not in result.covered_directories:
            errors.append(_error(ReasonCode.COMPLETE_ROOT_NOT_COVERED))
    elif result.status is ScanStatus.PARTIAL:
        if not any(failure.compromises_coverage for failure in result.failures):
            errors.append(_error(ReasonCode.PARTIAL_WITHOUT_COVERAGE_FAILURE))
    elif result.status is ScanStatus.ROOT_UNAVAILABLE:
        if result.entries or result.covered_directories:
            errors.append(_error(ReasonCode.UNAVAILABLE_ROOT_HAS_OBSERVATIONS))
        if not any(
            failure.operation is FailureOperation.OBSERVE_ROOT for failure in result.failures
        ):
            errors.append(_error(ReasonCode.ROOT_FAILURE_REQUIRED))
    elif result.status is ScanStatus.FAILED:
        if result.entries or result.covered_directories:
            errors.append(_error(ReasonCode.FAILED_HAS_OBSERVATIONS))
        if not any(
            failure.operation is FailureOperation.ENUMERATE_DIRECTORY for failure in result.failures
        ):
            errors.append(_error(ReasonCode.ROOT_FAILURE_REQUIRED))


def _coverage(result: ScanResult, valid: bool) -> CoverageClassification:
    if not valid:
        return CoverageClassification.INVALID
    if result.status is ScanStatus.COMPLETE:
        return (
            CoverageClassification.COMPLETE_RECURSIVE_SCOPE
            if result.scope.recursive
            else CoverageClassification.COMPLETE_NON_RECURSIVE_SCOPE
        )
    return {
        ScanStatus.PARTIAL: CoverageClassification.PARTIAL,
        ScanStatus.CANCELLED: CoverageClassification.CANCELLED,
        ScanStatus.ROOT_UNAVAILABLE: CoverageClassification.ROOT_UNAVAILABLE,
        ScanStatus.FAILED: CoverageClassification.FAILED,
    }[result.status]


def _potential_hardlinks(
    entries: tuple[EntryObservation, ...],
) -> tuple[EvidenceInference, ...]:
    groups: defaultdict[PhysicalIdentity, list[str]] = defaultdict(list)
    for entry in entries:
        if entry.entry_type is EntryType.FILE and entry.physical_identity is not None:
            groups[entry.physical_identity].append(entry.relative_path)
    return tuple(
        EvidenceInference(
            kind=InferenceKind.POTENTIAL_HARDLINK,
            relative_paths=tuple(sorted(paths)),
            physical_identity=identity,
        )
        for identity, paths in sorted(
            groups.items(), key=lambda item: (item[0].device, item[0].file_id)
        )
        if len(paths) > 1
    )


def _portability(
    result: ScanResult,
) -> tuple[tuple[PortabilityLimitation, ...], list[AssessmentReason]]:
    limitations = [
        PortabilityLimitation.PHYSICAL_IDENTITY_IS_HOST_SCOPED,
        PortabilityLimitation.FILESYSTEM_PATH_SEMANTICS_ARE_HOST_DEFINED,
    ]
    reasons: list[AssessmentReason] = []
    if result.environment is None:
        limitations.append(PortabilityLimitation.PLATFORM_OR_CONFINEMENT_UNRECORDED)
        reasons.append(_reason(ReasonCode.PLATFORM_PROVENANCE_MISSING))
    elif result.environment.confinement is ConfinementKind.PATH_BASED:
        limitations.append(PortabilityLimitation.PATH_BASED_CONFINEMENT_NOT_RACE_SAFE)
        reasons.append(_reason(ReasonCode.PATH_BASED_CONFINEMENT))
    elif result.environment.platform is HostPlatform.POSIX:
        reasons.append(_reason(ReasonCode.POSIX_CONFINEMENT_NOT_ATOMIC))
    return tuple(limitations), reasons


def _impediments(
    result: ScanResult,
    coverage: CoverageClassification,
    validation: StructuralValidation,
    portability: tuple[PortabilityLimitation, ...],
) -> tuple[DecisionImpediment, ...]:
    values: list[DecisionImpediment] = []
    if validation is StructuralValidation.INVALID:
        values.append(DecisionImpediment.STRUCTURALLY_INVALID)
    if coverage in {
        CoverageClassification.PARTIAL,
        CoverageClassification.CANCELLED,
        CoverageClassification.FAILED,
        CoverageClassification.INVALID,
    }:
        values.append(DecisionImpediment.INCOMPLETE_COVERAGE)
    if coverage is CoverageClassification.COMPLETE_NON_RECURSIVE_SCOPE:
        values.append(DecisionImpediment.NON_RECURSIVE_SCOPE)
    if coverage is CoverageClassification.ROOT_UNAVAILABLE:
        values.append(DecisionImpediment.ROOT_UNAVAILABLE)
    values.extend(
        (
            DecisionImpediment.ENUMERATION_NOT_ATOMIC,
            DecisionImpediment.CONTENT_NOT_VERIFIED,
            DecisionImpediment.LOGICAL_IDENTITY_UNCONFIRMED,
        )
    )
    if any(
        limitation
        in {
            PortabilityLimitation.PLATFORM_OR_CONFINEMENT_UNRECORDED,
            PortabilityLimitation.PATH_BASED_CONFINEMENT_NOT_RACE_SAFE,
        }
        for limitation in portability
    ):
        values.append(DecisionImpediment.CONFINEMENT_NOT_DEMONSTRATED)
    return tuple(dict.fromkeys(values))


def _valid_relative_path(value: object, *, allow_root: bool = False) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value == ".":
        return allow_root
    path = PurePosixPath(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _error(code: ReasonCode, path: str | None = None) -> AssessmentReason:
    return AssessmentReason(code=code, severity=ReasonSeverity.ERROR, relative_path=path)


def _reason(code: ReasonCode, path: str | None = None) -> AssessmentReason:
    return AssessmentReason(code=code, severity=ReasonSeverity.INFORMATION, relative_path=path)
