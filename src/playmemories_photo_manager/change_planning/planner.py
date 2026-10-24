"""Pure, conservative comparison of assessed evidence and catalog state."""

from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import PurePosixPath

from playmemories_photo_manager.catalog import (
    Asset,
    AssetKind,
    FileLocation,
    HashState,
    LibraryRoot,
    LocationAvailability,
    RootAvailability,
)
from playmemories_photo_manager.catalog import (
    EntryType as CatalogEntryType,
)
from playmemories_photo_manager.evidence import (
    CoverageClassification,
    EvidenceAssessment,
    StructuralValidation,
)
from playmemories_photo_manager.scanner import (
    EntryObservation,
    EntryType,
    PhysicalIdentity,
    RootObservation,
    ScanScope,
    ScanStatus,
)

from .models import (
    CatalogChangePlan,
    CatalogSnapshot,
    ChangeClassification,
    DiagnosticCode,
    DiagnosticSeverity,
    LocationPhysicalEvidence,
    PlanDiagnostic,
    PlannedChange,
    PlanningContext,
    PlanStatus,
)


def plan_changes(
    assessment: EvidenceAssessment,
    catalog_snapshot: CatalogSnapshot,
    context: PlanningContext,
) -> CatalogChangePlan:
    """Return proposals and diagnostics without I/O, mutation, or generated identities."""
    if not isinstance(assessment, EvidenceAssessment):
        raise TypeError("assessment must be EvidenceAssessment")
    if not isinstance(catalog_snapshot, CatalogSnapshot):
        raise TypeError("catalog_snapshot must be CatalogSnapshot")
    if not isinstance(context, PlanningContext):
        raise TypeError("context must be PlanningContext")

    diagnostics: list[PlanDiagnostic] = []
    diagnostics.extend(_validate_assessment(assessment))
    diagnostics.extend(_validate_context(assessment, catalog_snapshot, context))
    diagnostics.extend(_validate_snapshot(catalog_snapshot))

    if assessment.structural_validation is StructuralValidation.INVALID:
        diagnostics.append(_error(DiagnosticCode.INVALID_ASSESSMENT))
    if assessment.coverage is CoverageClassification.ROOT_UNAVAILABLE:
        diagnostics.append(_warning(DiagnosticCode.ROOT_UNAVAILABLE))
    elif assessment.coverage in {
        CoverageClassification.PARTIAL,
        CoverageClassification.CANCELLED,
        CoverageClassification.FAILED,
    }:
        diagnostics.append(_warning(DiagnosticCode.INCOMPLETE_COVERAGE))

    blocking = any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics)
    changes = _blocked_changes(assessment) if blocking else _compare(assessment, catalog_snapshot)
    all_diagnostics = tuple(
        diagnostics
        + [
            _information(DiagnosticCode.CONTENT_NOT_VERIFIED),
            _information(DiagnosticCode.ABSENCE_NOT_AUTHORIZED),
        ]
    )
    status = _plan_status(changes, all_diagnostics)
    return CatalogChangePlan(
        run_id=assessment.run_id,
        library_root_id=context.library_root_id,
        scope=context.scope,
        snapshot_read_version=catalog_snapshot.read_version,
        status=status,
        changes=changes,
        diagnostics=all_diagnostics,
    )


def _validate_context(
    assessment: EvidenceAssessment, snapshot: CatalogSnapshot, context: PlanningContext
) -> list[PlanDiagnostic]:
    errors: list[PlanDiagnostic] = []
    if (
        not _uuid4(context.library_root_id)
        or not isinstance(context.catalog_root_path, str)
        or not context.catalog_root_path
        or not isinstance(context.observed_root_path, str)
        or not context.observed_root_path
        or not isinstance(context.scope, ScanScope)
        or (
            context.catalog_root_identity is not None
            and not _valid_identity(context.catalog_root_identity)
        )
    ):
        errors.append(_error(DiagnosticCode.INVALID_CONTEXT))
        return errors
    if not isinstance(snapshot.library_root, LibraryRoot):
        return errors
    if context.library_root_id != snapshot.library_root.id:
        errors.append(_error(DiagnosticCode.ROOT_ID_MISMATCH))
    if context.catalog_root_path != snapshot.library_root.normalized_path:
        errors.append(_error(DiagnosticCode.ROOT_PATH_MISMATCH))
    if assessment.root is None:
        if assessment.original_status is not ScanStatus.ROOT_UNAVAILABLE:
            errors.append(_error(DiagnosticCode.INVALID_ASSESSMENT))
    else:
        if context.observed_root_path != assessment.root.absolute_path:
            errors.append(_error(DiagnosticCode.ROOT_PATH_MISMATCH))
        if context.catalog_root_path != context.observed_root_path:
            errors.append(_error(DiagnosticCode.ROOT_PATH_MISMATCH))
        observed_identity = assessment.root.physical_identity
        if context.catalog_root_identity is None or observed_identity is None:
            errors.append(_warning(DiagnosticCode.ROOT_IDENTITY_UNAVAILABLE))
        elif context.catalog_root_identity != observed_identity:
            errors.append(_error(DiagnosticCode.ROOT_IDENTITY_MISMATCH))
    if context.scope != assessment.scope or context.scope != snapshot.effective_scope:
        errors.append(_error(DiagnosticCode.SCOPE_MISMATCH))
    return errors


def _validate_assessment(assessment: EvidenceAssessment) -> list[PlanDiagnostic]:
    if (
        not _uuid4(assessment.run_id)
        or not isinstance(assessment.original_status, ScanStatus)
        or not isinstance(assessment.structural_validation, StructuralValidation)
        or not isinstance(assessment.coverage, CoverageClassification)
        or not isinstance(assessment.scope, ScanScope)
        or (assessment.root is not None and not isinstance(assessment.root, RootObservation))
        or not isinstance(assessment.accepted_entries, tuple)
        or not isinstance(assessment.inconclusive_entries, tuple)
        or not all(isinstance(item, EntryObservation) for item in assessment.accepted_entries)
        or not all(isinstance(item, EntryObservation) for item in assessment.inconclusive_entries)
    ):
        return [_error(DiagnosticCode.INVALID_ASSESSMENT)]
    return []


def _validate_snapshot(snapshot: CatalogSnapshot) -> list[PlanDiagnostic]:
    errors: list[PlanDiagnostic] = []
    if (
        not isinstance(snapshot.library_root, LibraryRoot)
        or not isinstance(snapshot.assets, tuple)
        or not isinstance(snapshot.locations, tuple)
        or not isinstance(snapshot.physical_evidence, tuple)
        or not isinstance(snapshot.effective_scope, ScanScope)
        or (snapshot.read_version is not None and not isinstance(snapshot.read_version, str))
    ):
        return [_error(DiagnosticCode.INVALID_SNAPSHOT)]

    asset_ids: set[str] = set()
    location_ids: set[str] = set()
    paths: defaultdict[str, list[FileLocation]] = defaultdict(list)
    malformed = (
        not _uuid4(snapshot.library_root.id)
        or not isinstance(snapshot.library_root.normalized_path, str)
        or not snapshot.library_root.normalized_path
        or not isinstance(snapshot.library_root.availability, RootAvailability)
        or snapshot.effective_scope.follows_links
        or not _valid_scope_path(snapshot.effective_scope.relative_path)
        or not isinstance(snapshot.effective_scope.recursive, bool)
    )
    for asset in snapshot.assets:
        if (
            not isinstance(asset, Asset)
            or not _uuid4(asset.id)
            or asset.id in asset_ids
            or not isinstance(asset.kind, AssetKind)
            or not isinstance(asset.hash_state, HashState)
        ):
            malformed = True
            continue
        asset_ids.add(asset.id)
    for location in snapshot.locations:
        if not isinstance(location, FileLocation):
            malformed = True
            continue
        if (
            not _uuid4(location.id)
            or location.id in location_ids
            or location.asset_id not in asset_ids
            or location.library_root_id != snapshot.library_root.id
            or not _valid_path(location.normalized_relative_path)
            or not _in_scope(location.normalized_relative_path, snapshot.effective_scope)
            or not isinstance(location.availability, LocationAvailability)
            or not isinstance(location.entry_type, CatalogEntryType)
        ):
            malformed = True
        location_ids.add(location.id)
        paths[location.normalized_relative_path].append(location)
    evidence_ids: set[str] = set()
    identity_owners: defaultdict[PhysicalIdentity, set[str]] = defaultdict(set)
    for evidence in snapshot.physical_evidence:
        if (
            not isinstance(evidence, LocationPhysicalEvidence)
            or evidence.location_id not in location_ids
            or evidence.location_id in evidence_ids
            or not _valid_identity(evidence.identity)
        ):
            malformed = True
            continue
        evidence_ids.add(evidence.location_id)
        location = next(item for item in snapshot.locations if item.id == evidence.location_id)
        if location.availability is not LocationAvailability.MISSING:
            identity_owners[evidence.identity].add(location.asset_id)
    if malformed:
        errors.append(_error(DiagnosticCode.INVALID_SNAPSHOT))
    if any(len(asset_ids) > 1 for asset_ids in identity_owners.values()):
        errors.append(_error(DiagnosticCode.PHYSICAL_IDENTITY_CONTRADICTION))
    for path, locations in sorted(paths.items()):
        active = [
            item for item in locations if item.availability is not LocationAvailability.MISSING
        ]
        if len(active) > 1:
            errors.append(
                _error(
                    DiagnosticCode.ACTIVE_LOCATION_CONFLICT,
                    path,
                    tuple(sorted(item.id for item in active)),
                )
            )
        if len({item.id for item in locations}) != len(locations):
            errors.append(_error(DiagnosticCode.PATH_COLLISION, path))
    return errors


def _compare(
    assessment: EvidenceAssessment, snapshot: CatalogSnapshot
) -> tuple[PlannedChange, ...]:
    by_path: defaultdict[str, list[FileLocation]] = defaultdict(list)
    for location in snapshot.locations:
        by_path[location.normalized_relative_path].append(location)
    identities = {item.location_id: item.identity for item in snapshot.physical_evidence}
    changes: list[PlannedChange] = []
    for entry in sorted(assessment.accepted_entries, key=lambda item: item.relative_path):
        if entry.entry_type is not EntryType.FILE:
            changes.append(
                PlannedChange(
                    ChangeClassification.INCONCLUSIVE,
                    entry.relative_path,
                    entry,
                    diagnostics=(
                        _warning(DiagnosticCode.NON_FILE_OBSERVATION, entry.relative_path),
                    ),
                )
            )
            continue
        locations = by_path.get(entry.relative_path, [])
        active = [
            item for item in locations if item.availability is not LocationAvailability.MISSING
        ]
        if active:
            location = active[0]
            known_identity = identities.get(location.id)
            if (
                known_identity is not None
                and entry.physical_identity is not None
                and known_identity != entry.physical_identity
            ):
                changes.append(
                    PlannedChange(
                        ChangeClassification.BLOCKED,
                        entry.relative_path,
                        entry,
                        location.asset_id,
                        location.id,
                        (
                            _error(
                                DiagnosticCode.PHYSICAL_IDENTITY_CONTRADICTION,
                                entry.relative_path,
                            ),
                        ),
                    )
                )
            else:
                item_diagnostics = ()
                if known_identity is not None and entry.physical_identity is None:
                    item_diagnostics = (
                        _warning(DiagnosticCode.PHYSICAL_IDENTITY_UNAVAILABLE, entry.relative_path),
                    )
                changes.append(
                    PlannedChange(
                        ChangeClassification.KNOWN_LOCATION_OBSERVED,
                        entry.relative_path,
                        entry,
                        location.asset_id,
                        location.id,
                        item_diagnostics,
                    )
                )
        else:
            item_diagnostics = ()
            if locations:
                item_diagnostics = (
                    _information(DiagnosticCode.PREVIOUSLY_MISSING_PATH, entry.relative_path),
                )
            changes.append(
                PlannedChange(
                    ChangeClassification.NEW_FILE_CANDIDATE,
                    entry.relative_path,
                    entry,
                    diagnostics=item_diagnostics,
                )
            )
    for entry in sorted(assessment.inconclusive_entries, key=lambda item: item.relative_path):
        changes.append(
            PlannedChange(
                ChangeClassification.INCONCLUSIVE,
                entry.relative_path,
                entry,
                diagnostics=(_warning(DiagnosticCode.INCONCLUSIVE_EVIDENCE, entry.relative_path),),
            )
        )
    return tuple(changes)


def _blocked_changes(assessment: EvidenceAssessment) -> tuple[PlannedChange, ...]:
    entries = assessment.accepted_entries + assessment.inconclusive_entries
    return tuple(
        PlannedChange(
            ChangeClassification.BLOCKED,
            entry.relative_path,
            entry,
            diagnostics=(_error(DiagnosticCode.INVALID_ASSESSMENT, entry.relative_path),),
        )
        for entry in sorted(entries, key=lambda item: item.relative_path)
    )


def _plan_status(
    changes: tuple[PlannedChange, ...], diagnostics: tuple[PlanDiagnostic, ...]
) -> PlanStatus:
    if any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics) or any(
        item.classification is ChangeClassification.BLOCKED for item in changes
    ):
        return PlanStatus.BLOCKED
    if (
        any(item.classification is ChangeClassification.INCONCLUSIVE for item in changes)
        or any(item.severity is DiagnosticSeverity.WARNING for item in diagnostics)
        or any(
            diagnostic.severity is DiagnosticSeverity.WARNING
            for item in changes
            for diagnostic in item.diagnostics
        )
    ):
        return PlanStatus.INCONCLUSIVE
    return PlanStatus.READY


def _uuid4(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        identifier = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return identifier.version == 4 and str(identifier) == value


def _valid_path(value: object) -> bool:
    if not isinstance(value, str) or not value or value == ".":
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _valid_scope_path(value: object) -> bool:
    return value == "." or _valid_path(value)


def _in_scope(path: str, scope: ScanScope) -> bool:
    inside = True if scope.relative_path == "." else path.startswith(f"{scope.relative_path}/")
    if not inside:
        return False
    if scope.recursive:
        return True
    parent = PurePosixPath(path).parent.as_posix()
    return parent == scope.relative_path


def _valid_identity(identity: object) -> bool:
    return (
        isinstance(identity, PhysicalIdentity)
        and isinstance(identity.device, int)
        and not isinstance(identity.device, bool)
        and identity.device >= 0
        and isinstance(identity.file_id, int)
        and not isinstance(identity.file_id, bool)
        and identity.file_id > 0
    )


def _diagnostic(
    code: DiagnosticCode,
    severity: DiagnosticSeverity,
    path: str | None = None,
    location_ids: tuple[str, ...] = (),
) -> PlanDiagnostic:
    return PlanDiagnostic(code, severity, path, location_ids)


def _error(
    code: DiagnosticCode, path: str | None = None, location_ids: tuple[str, ...] = ()
) -> PlanDiagnostic:
    return _diagnostic(code, DiagnosticSeverity.ERROR, path, location_ids)


def _warning(code: DiagnosticCode, path: str | None = None) -> PlanDiagnostic:
    return _diagnostic(code, DiagnosticSeverity.WARNING, path)


def _information(code: DiagnosticCode, path: str | None = None) -> PlanDiagnostic:
    return _diagnostic(code, DiagnosticSeverity.INFORMATION, path)
