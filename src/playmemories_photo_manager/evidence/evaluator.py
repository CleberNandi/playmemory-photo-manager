"""Pure validation and classification of scanner evidence."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import PurePosixPath

from playmemories_photo_manager.scanner import (
    ConfinementKind,
    EntryObservation,
    EntryType,
    EvidenceKind,
    FailureKind,
    FailureOperation,
    HostPlatform,
    ObservationFailure,
    ObservedTimestamps,
    PhysicalIdentity,
    RootObservation,
    ScanEnvironment,
    ScanResult,
    ScanScope,
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
    if not _validate_contract_types(scan_result, errors):
        return EvidenceAssessment(
            run_id=scan_result.run_id if isinstance(scan_result.run_id, str) else "",
            original_status=scan_result.status,
            root=scan_result.root if isinstance(scan_result.root, RootObservation) else None,
            scope=scan_result.scope,
            coverage=CoverageClassification.INVALID,
            structural_validation=StructuralValidation.INVALID,
            accepted_entries=(),
            inconclusive_entries=(
                scan_result.entries if isinstance(scan_result.entries, tuple) else ()
            ),
            failures=scan_result.failures if isinstance(scan_result.failures, tuple) else (),
            inferences=(),
            reasons=tuple(errors),
            portability_limitations=(PortabilityLimitation.PLATFORM_OR_CONFINEMENT_UNRECORDED,),
            decision_impediments=(
                DecisionImpediment.STRUCTURALLY_INVALID,
                DecisionImpediment.INCOMPLETE_COVERAGE,
                DecisionImpediment.ENUMERATION_NOT_ATOMIC,
                DecisionImpediment.CONTENT_NOT_VERIFIED,
                DecisionImpediment.LOGICAL_IDENTITY_UNCONFIRMED,
                DecisionImpediment.CONFINEMENT_NOT_DEMONSTRATED,
            ),
        )
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
        root=scan_result.root,
        scope=scan_result.scope,
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


def _validate_contract_types(result: ScanResult, errors: list[AssessmentReason]) -> bool:
    """Reject manually assembled contracts before semantic validation dereferences them."""
    valid = True

    def require(condition: bool, path: str | None = None) -> None:
        nonlocal valid
        if not condition:
            valid = False
            errors.append(_error(ReasonCode.INVALID_CONTRACT_TYPE, path))

    require(isinstance(result.run_id, str))
    require(isinstance(result.started_at, datetime))
    require(isinstance(result.finished_at, datetime))
    require(isinstance(result.status, ScanStatus))
    require(isinstance(result.scope, ScanScope))
    require(result.root is None or isinstance(result.root, RootObservation))
    require(isinstance(result.covered_directories, tuple))
    require(isinstance(result.entries, tuple))
    require(isinstance(result.failures, tuple))
    require(result.environment is None or isinstance(result.environment, ScanEnvironment))
    if not valid:
        return False

    require(isinstance(result.scope.relative_path, str))
    require(isinstance(result.scope.recursive, bool))
    require(isinstance(result.scope.follows_links, bool))
    require(all(isinstance(path, str) for path in result.covered_directories))
    for entry in result.entries:
        require(isinstance(entry, EntryObservation))
        if isinstance(entry, EntryObservation):
            require(isinstance(entry.relative_path, str))
            require(isinstance(entry.entry_type, EntryType), entry.relative_path)
            require(isinstance(entry.timestamps, ObservedTimestamps), entry.relative_path)
            require(
                entry.physical_identity is None
                or isinstance(entry.physical_identity, PhysicalIdentity),
                entry.relative_path,
            )
            require(isinstance(entry.evidence_kind, EvidenceKind), entry.relative_path)
    for failure in result.failures:
        require(isinstance(failure, ObservationFailure))
        if isinstance(failure, ObservationFailure):
            require(failure.relative_path is None or isinstance(failure.relative_path, str))
            require(isinstance(failure.operation, FailureOperation), failure.relative_path)
            require(isinstance(failure.kind, FailureKind), failure.relative_path)
            require(isinstance(failure.compromises_coverage, bool), failure.relative_path)
            require(
                failure.error_code is None
                or (
                    isinstance(failure.error_code, int) and not isinstance(failure.error_code, bool)
                ),
                failure.relative_path,
            )
    if result.root is not None:
        require(isinstance(result.root.requested_path, str))
        require(isinstance(result.root.absolute_path, str))
        require(
            result.root.physical_identity is None
            or isinstance(result.root.physical_identity, PhysicalIdentity)
        )
    if result.environment is not None:
        require(isinstance(result.environment.platform, HostPlatform))
        require(isinstance(result.environment.confinement, ConfinementKind))
    return valid


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
    if result.root is not None:
        _validate_physical_identity(result.root.physical_identity, None, errors)
    if (
        result.environment is not None
        and result.environment.confinement is ConfinementKind.DESCRIPTOR_RELATIVE
        and result.environment.platform is not HostPlatform.POSIX
    ):
        errors.append(_error(ReasonCode.INVALID_ENVIRONMENT))


def _validate_paths_and_entries(result: ScanResult, errors: list[AssessmentReason]) -> None:
    if not _valid_relative_path(result.scope.relative_path, allow_root=True):
        errors.append(_error(ReasonCode.INVALID_SCOPE_PATH, result.scope.relative_path))
    if result.scope.follows_links:
        errors.append(_error(ReasonCode.LINKS_FOLLOWED))

    entry_paths: set[str] = set()
    directory_paths: set[str] = set()
    identities: defaultdict[PhysicalIdentity, list[EntryObservation]] = defaultdict(list)
    for entry in result.entries:
        path = entry.relative_path
        if not _valid_relative_path(path):
            errors.append(_error(ReasonCode.INVALID_ENTRY_PATH, path))
        if path in entry_paths:
            errors.append(_error(ReasonCode.DUPLICATE_ENTRY_PATH, path))
        entry_paths.add(path)
        valid_path = _valid_relative_path(path)
        outside_scope = valid_path and not _path_is_in_scope(path, result.scope.relative_path)
        too_deep = (
            valid_path
            and not result.scope.recursive
            and _parent_path(path) != result.scope.relative_path
        )
        if outside_scope or too_deep:
            errors.append(_error(ReasonCode.PATH_OUTSIDE_SCOPE, path))
        if entry.entry_type is EntryType.DIRECTORY:
            directory_paths.add(path)
        _validate_entry(entry, errors)
        if entry.physical_identity is not None and _physical_identity_valid(
            entry.physical_identity
        ):
            identities[entry.physical_identity].append(entry)

    covered = set(result.covered_directories)
    if len(covered) != len(result.covered_directories):
        errors.append(_error(ReasonCode.DUPLICATE_COVERED_DIRECTORY))
    for path in result.covered_directories:
        if not _valid_relative_path(path, allow_root=True):
            errors.append(_error(ReasonCode.INVALID_COVERED_DIRECTORY, path))
        elif path != "." and path not in directory_paths and path != result.scope.relative_path:
            errors.append(_error(ReasonCode.COVERED_DIRECTORY_NOT_OBSERVED, path))
        valid_path = _valid_relative_path(path, allow_root=True)
        outside_scope = valid_path and not _directory_is_in_scope(path, result.scope.relative_path)
        too_deep = path != result.scope.relative_path and not result.scope.recursive
        if outside_scope or too_deep:
            errors.append(_error(ReasonCode.PATH_OUTSIDE_SCOPE, path))
    for path in sorted(entry_paths):
        parent = _parent_path(path)
        if parent != result.scope.relative_path and parent not in directory_paths:
            errors.append(_error(ReasonCode.ENTRY_PARENT_NOT_OBSERVED, path))
    if result.status is ScanStatus.COMPLETE and result.scope.recursive:
        for path in sorted(directory_paths - covered):
            errors.append(_error(ReasonCode.DIRECTORY_NOT_COVERED, path))
    for failure in result.failures:
        if failure.relative_path is not None and not _valid_relative_path(
            failure.relative_path, allow_root=True
        ):
            errors.append(_error(ReasonCode.INVALID_FAILURE_PATH, failure.relative_path))
        elif failure.relative_path is not None and not _directory_is_in_scope(
            failure.relative_path, result.scope.relative_path
        ):
            errors.append(_error(ReasonCode.PATH_OUTSIDE_SCOPE, failure.relative_path))
    for entries in identities.values():
        types = {entry.entry_type for entry in entries}
        sizes = {entry.byte_size for entry in entries if entry.entry_type is EntryType.FILE}
        if len(types) > 1 or len(sizes) > 1:
            for entry in entries:
                errors.append(
                    _error(ReasonCode.PHYSICAL_IDENTITY_CONTRADICTION, entry.relative_path)
                )


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
    for value in (
        entry.timestamps.modified_ns,
        entry.timestamps.accessed_ns,
        entry.timestamps.changed_ns,
    ):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            errors.append(_error(ReasonCode.INVALID_TIMESTAMP, entry.relative_path))
            break
    _validate_physical_identity(entry.physical_identity, entry.relative_path, errors)


def _validate_physical_identity(
    identity: PhysicalIdentity | None,
    path: str | None,
    errors: list[AssessmentReason],
) -> None:
    if identity is not None and not _physical_identity_valid(identity):
        errors.append(_error(ReasonCode.INVALID_PHYSICAL_IDENTITY, path))


def _physical_identity_valid(identity: PhysicalIdentity | None) -> bool:
    return identity is None or not (
        isinstance(identity.device, bool)
        or not isinstance(identity.device, int)
        or identity.device < 0
        or isinstance(identity.file_id, bool)
        or not isinstance(identity.file_id, int)
        or identity.file_id <= 0
    )


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
        if any(
            entry.evidence_kind is not EvidenceKind.DIRECT_OBSERVATION for entry in result.entries
        ):
            errors.append(_error(ReasonCode.COMPLETE_HAS_NON_DIRECT_EVIDENCE))
        if result.scope.relative_path not in result.covered_directories:
            errors.append(_error(ReasonCode.COMPLETE_ROOT_NOT_COVERED))
    elif result.status is ScanStatus.PARTIAL:
        if not any(failure.compromises_coverage for failure in result.failures):
            errors.append(_error(ReasonCode.PARTIAL_WITHOUT_COVERAGE_FAILURE))
    elif result.status is ScanStatus.ROOT_UNAVAILABLE:
        if result.entries or result.covered_directories:
            errors.append(_error(ReasonCode.UNAVAILABLE_ROOT_HAS_OBSERVATIONS))
        if not any(
            failure.operation is FailureOperation.OBSERVE_ROOT and failure.compromises_coverage
            for failure in result.failures
        ):
            errors.append(_error(ReasonCode.ROOT_FAILURE_REQUIRED))
    elif result.status is ScanStatus.FAILED:
        if result.entries or result.covered_directories:
            errors.append(_error(ReasonCode.FAILED_HAS_OBSERVATIONS))
        if not any(
            failure.operation is FailureOperation.ENUMERATE_DIRECTORY
            and failure.compromises_coverage
            for failure in result.failures
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


def _path_is_in_scope(value: str, scope: str) -> bool:
    return scope == "." or value.startswith(f"{scope}/")


def _directory_is_in_scope(value: str, scope: str) -> bool:
    return value == scope or _path_is_in_scope(value, scope)


def _parent_path(value: str) -> str:
    parent = PurePosixPath(value).parent.as_posix()
    return "." if parent == "." else parent


def _error(code: ReasonCode, path: str | None = None) -> AssessmentReason:
    return AssessmentReason(code=code, severity=ReasonSeverity.ERROR, relative_path=path)


def _reason(code: ReasonCode, path: str | None = None) -> AssessmentReason:
    return AssessmentReason(code=code, severity=ReasonSeverity.INFORMATION, relative_path=path)
