"""Vertical scan, planning, authorization, and transactional application flow."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath

from playmemories_photo_manager.catalog import (
    AssetKind,
    Catalog,
    CatalogError,
)
from playmemories_photo_manager.catalog.errors import CatalogStateConflictError
from playmemories_photo_manager.catalog.models import (
    FileRegistrationDisposition,
    NewFileRegistration,
)
from playmemories_photo_manager.change_planning import (
    CatalogChangePlan,
    CatalogSnapshot,
    ChangeClassification,
    DiagnosticCode,
    DiagnosticSeverity,
    PlanningContext,
    PlanStatus,
    plan_changes,
)
from playmemories_photo_manager.evidence import (
    DecisionImpediment,
    StructuralValidation,
    evaluate,
)
from playmemories_photo_manager.scanner import (
    PhysicalIdentity,
    ScanOptions,
    ScanResult,
    ScanScope,
    scan,
)

from .models import (
    CandidateReference,
    CandidateSelection,
    IngestionAuthorization,
    IngestionAuthorizationError,
    IngestionBatchStatus,
    IngestionItemDisposition,
    IngestionItemResult,
    IngestionProposal,
    IngestionReport,
)


def prepare_ingestion(
    catalog: Catalog,
    library_root_id: str,
    filesystem_root: str,
    options: ScanOptions | None = None,
) -> IngestionProposal:
    """Observe one explicit root and prepare a conservative catalog change plan."""
    root = catalog.get_root(library_root_id)
    scan_result = scan(filesystem_root, options)
    assessment = evaluate(scan_result)
    snapshot = _catalog_snapshot(catalog, library_root_id, assessment.scope)
    observed_path = scan_result.root.absolute_path if scan_result.root else filesystem_root
    context = PlanningContext(
        library_root_id=library_root_id,
        catalog_root_path=root.normalized_path,
        observed_root_path=observed_path,
        scope=assessment.scope,
        catalog_root_identity=None,
    )
    return prepare_from_snapshot(snapshot, scan_result, context)


def prepare_from_snapshot(
    snapshot: CatalogSnapshot, scan_result: ScanResult, context: PlanningContext
) -> IngestionProposal:
    """Pure assembly after the worker has closed its SQLite snapshot connection."""
    assessment = evaluate(scan_result)
    return IngestionProposal(
        scan_result=scan_result,
        assessment=assessment,
        catalog_snapshot=snapshot,
        planning_context=context,
        plan=plan_changes(assessment, snapshot, context),
    )


def candidate_reference(plan: CatalogChangePlan, relative_path: str) -> CandidateReference:
    """Build a stable, non-positional reference to one candidate in a plan."""
    return CandidateReference(plan.run_id, plan.library_root_id, relative_path)


def authorize_ingestion(
    plan: CatalogChangePlan, selections: tuple[CandidateSelection, ...]
) -> IngestionAuthorization:
    """Explicitly authorize a known subset of new-file candidates."""
    _require_applicable_plan(plan)
    if not isinstance(selections, tuple) or not all(
        isinstance(item, CandidateSelection) for item in selections
    ):
        raise IngestionAuthorizationError("selections must be a tuple of CandidateSelection")
    candidates = {
        item.relative_path
        for item in plan.changes
        if item.classification is ChangeClassification.NEW_FILE_CANDIDATE
    }
    seen: set[str] = set()
    for selection in selections:
        reference = selection.candidate
        if not isinstance(reference, CandidateReference) or (
            reference.run_id,
            reference.library_root_id,
        ) != (plan.run_id, plan.library_root_id):
            raise IngestionAuthorizationError("candidate does not reference this plan")
        if reference.relative_path not in candidates:
            raise IngestionAuthorizationError("candidate is not present in this plan")
        if reference.relative_path in seen:
            raise IngestionAuthorizationError("candidate selections must be unique")
        seen.add(reference.relative_path)
        if not isinstance(selection.asset_kind, AssetKind):
            raise IngestionAuthorizationError("asset kind must be explicit")
        if selection.media_type is not None and not isinstance(selection.media_type, str):
            raise IngestionAuthorizationError("media type must be a string or null")
    fingerprint = plan_fingerprint(plan)
    ordered = tuple(sorted(selections, key=lambda item: item.candidate.relative_path))
    return IngestionAuthorization(
        fingerprint,
        plan.run_id,
        plan.library_root_id,
        ordered,
        _decision_fingerprint(fingerprint, plan.run_id, plan.library_root_id, ordered),
    )


def apply_ingestion(
    catalog: Catalog,
    proposal: IngestionProposal,
    authorization: IngestionAuthorization | None,
) -> IngestionReport:
    """Apply exactly the authorized plan candidates as one SQLite transaction."""
    validation_error = _proposal_error(proposal)
    fingerprint = plan_fingerprint(proposal.plan)
    base = (proposal.plan.run_id, proposal.plan.library_root_id, fingerprint)
    if validation_error is not None:
        return IngestionReport(
            *base,
            IngestionBatchStatus.REJECTED,
            _plan_items(proposal.plan, IngestionItemDisposition.BLOCKED, validation_error),
            validation_error,
        )

    candidate_changes = {
        item.relative_path: item
        for item in proposal.plan.changes
        if item.classification is ChangeClassification.NEW_FILE_CANDIDATE
    }
    if authorization is None:
        return IngestionReport(
            *base,
            IngestionBatchStatus.NO_AUTHORIZATION,
            _non_applied_items(proposal.plan, (), IngestionItemDisposition.IGNORED_NOT_AUTHORIZED),
            "explicit authorization was not supplied",
        )
    authorization_error = _authorization_error(proposal.plan, authorization, fingerprint)
    if authorization_error is not None:
        return IngestionReport(
            *base,
            IngestionBatchStatus.REJECTED,
            _non_applied_items(proposal.plan, (), IngestionItemDisposition.BLOCKED),
            authorization_error,
        )
    if not authorization.selections:
        return IngestionReport(
            *base,
            IngestionBatchStatus.EMPTY_SELECTION,
            _non_applied_items(proposal.plan, (), IngestionItemDisposition.IGNORED_NOT_AUTHORIZED),
        )

    selected = {item.candidate.relative_path: item for item in authorization.selections}
    registrations: list[NewFileRegistration] = []
    for path, selection in sorted(selected.items()):
        observation = candidate_changes[path].observation
        modified_ns = observation.timestamps.modified_ns
        if modified_ns is not None and modified_ns < 0:
            return IngestionReport(
                *base,
                IngestionBatchStatus.REJECTED,
                _non_applied_items(proposal.plan, selected, IngestionItemDisposition.BLOCKED),
                "negative filesystem mtime cannot be represented by the catalog schema",
            )
        registrations.append(
            NewFileRegistration(
                relative_path=path,
                kind=selection.asset_kind,
                byte_size=observation.byte_size,
                media_type=selection.media_type,
                filesystem_id=_physical_identity_text(observation.physical_identity),
                observed_mtime_ns=modified_ns,
            )
        )
    try:
        persisted = catalog._register_new_files_atomically(
            proposal.plan.library_root_id,
            proposal.assessment.root.absolute_path,
            tuple(registrations),
        )
    except CatalogStateConflictError as error:
        if _rollback_failed(error):
            return IngestionReport(
                *base,
                IngestionBatchStatus.TRANSACTION_FAILED,
                _non_applied_items(
                    proposal.plan,
                    selected,
                    IngestionItemDisposition.TRANSACTION_FAILED,
                ),
                f"{error}; rollback also failed and transaction state is uncertain",
            )
        conflicts = set(error.relative_paths) or set(selected)
        return IngestionReport(
            *base,
            IngestionBatchStatus.CONFLICT,
            tuple(
                IngestionItemResult(
                    candidate_reference(proposal.plan, path),
                    (
                        IngestionItemDisposition.CONFLICT
                        if path in selected
                        else IngestionItemDisposition.IGNORED_NOT_AUTHORIZED
                    ),
                    diagnostic=(
                        str(error)
                        if path in conflicts
                        else "authorized batch rolled back because another path conflicted"
                        if path in selected
                        else None
                    ),
                )
                for path in sorted(candidate_changes)
            ),
            str(error),
        )
    except CatalogError as error:
        return IngestionReport(
            *base,
            IngestionBatchStatus.TRANSACTION_FAILED,
            _non_applied_items(
                proposal.plan, selected, IngestionItemDisposition.TRANSACTION_FAILED
            ),
            str(error),
        )

    by_path = {result.location.normalized_relative_path: result for result in persisted}
    items: list[IngestionItemResult] = []
    for change in proposal.plan.changes:
        reference = candidate_reference(proposal.plan, change.relative_path)
        if change.classification is ChangeClassification.KNOWN_LOCATION_OBSERVED:
            items.append(
                IngestionItemResult(
                    reference,
                    IngestionItemDisposition.ALREADY_EXISTS,
                    change.asset_id,
                    change.location_id,
                )
            )
        elif change.classification is ChangeClassification.NEW_FILE_CANDIDATE:
            result = by_path.get(change.relative_path)
            if result is None:
                items.append(
                    IngestionItemResult(reference, IngestionItemDisposition.IGNORED_NOT_AUTHORIZED)
                )
            else:
                disposition = (
                    IngestionItemDisposition.CREATED
                    if result.disposition is FileRegistrationDisposition.CREATED
                    else IngestionItemDisposition.ALREADY_EXISTS
                )
                items.append(
                    IngestionItemResult(reference, disposition, result.asset.id, result.location.id)
                )
    return IngestionReport(*base, IngestionBatchStatus.APPLIED, tuple(items))


def plan_fingerprint(plan: CatalogChangePlan) -> str:
    """Return a deterministic correlation fingerprint, not an authorization token."""
    payload = {
        "run_id": plan.run_id,
        "root_id": plan.library_root_id,
        "scope": [plan.scope.relative_path, plan.scope.recursive, plan.scope.follows_links],
        "read_version": plan.snapshot_read_version,
        "status": str(plan.status),
        "changes": [
            [
                str(item.classification),
                item.relative_path,
                item.asset_id,
                item.location_id,
                str(item.observation.entry_type),
                item.observation.byte_size,
                item.observation.timestamps.modified_ns,
                (
                    None
                    if item.observation.physical_identity is None
                    else [
                        item.observation.physical_identity.device,
                        item.observation.physical_identity.file_id,
                    ]
                ),
            ]
            for item in plan.changes
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _catalog_snapshot(catalog: Catalog, root_id: str, scope: ScanScope) -> CatalogSnapshot:
    root = catalog.get_root(root_id)
    all_locations = []
    offset = 0
    while True:
        page = catalog.list_root_locations(root_id, limit=100, offset=offset)
        all_locations.extend(page)
        if len(page) < 100:
            break
        offset += len(page)
    locations = tuple(
        item for item in all_locations if _path_in_scope(item.normalized_relative_path, scope)
    )
    assets = tuple(
        catalog.get_asset(asset_id) for asset_id in sorted({item.asset_id for item in locations})
    )
    return CatalogSnapshot(
        root, assets, locations, (), scope, _snapshot_read_version(root, assets, locations)
    )


def _snapshot_read_version(root, assets, locations) -> str:
    version_payload = {
        "root": [root.id, root.normalized_path, str(root.availability)],
        "assets": [
            [
                item.id,
                str(item.kind),
                item.sha256,
                str(item.hash_state),
                item.byte_size,
                item.media_type,
                item.status,
            ]
            for item in assets
        ],
        "locations": [
            [
                item.id,
                item.asset_id,
                item.normalized_relative_path,
                str(item.entry_type),
                str(item.availability),
                item.observed_byte_size,
                item.observed_mtime_ns,
                item.filesystem_id,
            ]
            for item in sorted(locations, key=lambda value: value.id)
        ],
    }
    return hashlib.sha256(json.dumps(version_payload, separators=(",", ":")).encode()).hexdigest()


def _require_applicable_plan(plan: CatalogChangePlan) -> None:
    if not isinstance(plan, CatalogChangePlan):
        raise IngestionAuthorizationError("plan must be CatalogChangePlan")
    if plan.status is PlanStatus.BLOCKED or not _only_supported_inconclusiveness(plan):
        raise IngestionAuthorizationError("plan is not eligible for ingestion")
    if any(
        item.classification in {ChangeClassification.BLOCKED, ChangeClassification.INCONCLUSIVE}
        for item in plan.changes
    ):
        raise IngestionAuthorizationError("plan contains blocked or inconclusive changes")


def _only_supported_inconclusiveness(plan: CatalogChangePlan) -> bool:
    if plan.status is PlanStatus.READY:
        return True
    if plan.status is not PlanStatus.INCONCLUSIVE:
        return False
    warning_codes = {
        item.code for item in plan.diagnostics if item.severity is DiagnosticSeverity.WARNING
    }
    return warning_codes == {DiagnosticCode.ROOT_IDENTITY_UNAVAILABLE}


def _proposal_error(proposal: IngestionProposal) -> str | None:
    error = _proposal_evidence_error(proposal)
    if error is not None:
        return error
    try:
        _require_applicable_plan(proposal.plan)
    except IngestionAuthorizationError as error:
        return str(error)
    return None


def _proposal_evidence_error(proposal: IngestionProposal) -> str | None:
    """Shared evidence checks, separate from the unchanged legacy applicability gate."""
    if not isinstance(proposal, IngestionProposal):
        return "proposal must be IngestionProposal"
    if proposal.assessment != evaluate(proposal.scan_result):
        return "assessment does not match the original scan result"
    if proposal.assessment.structural_validation is not StructuralValidation.VALID:
        return "assessment is structurally invalid"
    unsupported_impediments = {
        DecisionImpediment.STRUCTURALLY_INVALID,
        DecisionImpediment.INCOMPLETE_COVERAGE,
        DecisionImpediment.ROOT_UNAVAILABLE,
        DecisionImpediment.CONFINEMENT_NOT_DEMONSTRATED,
    }.intersection(proposal.assessment.decision_impediments)
    if unsupported_impediments:
        values = ", ".join(sorted(str(item) for item in unsupported_impediments))
        return f"assessment has unsupported decision impediments: {values}"
    try:
        expected_plan = plan_changes(
            proposal.assessment,
            proposal.catalog_snapshot,
            proposal.planning_context,
        )
    except (AttributeError, TypeError, ValueError):
        return "proposal contains malformed planning inputs"
    if proposal.plan != expected_plan:
        return "plan does not match its assessment and catalog snapshot"
    locations_by_id = {item.id: item for item in proposal.catalog_snapshot.locations}
    for change in proposal.plan.changes:
        if change.classification is not ChangeClassification.KNOWN_LOCATION_OBSERVED:
            continue
        location = locations_by_id.get(change.location_id)
        if location is None:
            return "known plan location is absent from the catalog snapshot"
        observed_identity = _physical_identity_text(change.observation.physical_identity)
        if location.filesystem_id is not None and (
            not location.filesystem_id.startswith("scanner:")
            or observed_identity != location.filesystem_id
        ):
            return f"physical identity changed at active path: {change.relative_path}"
        if (
            location.observed_byte_size != change.observation.byte_size
            or location.observed_mtime_ns != change.observation.timestamps.modified_ns
        ):
            return f"observed attributes changed at active path: {change.relative_path}"
    if proposal.scan_result.run_id != proposal.plan.run_id:
        return "plan does not reference the original scan run"
    if proposal.scan_result.scope != proposal.plan.scope:
        return "plan scope does not match the original scan run"
    return None


def _authorization_error(
    plan: CatalogChangePlan, authorization: IngestionAuthorization, fingerprint: str
) -> str | None:
    if not isinstance(authorization, IngestionAuthorization):
        return "authorization must be IngestionAuthorization"
    if (
        authorization.plan_fingerprint != fingerprint
        or authorization.run_id != plan.run_id
        or authorization.library_root_id != plan.library_root_id
    ):
        return "authorization does not reference this concrete plan"
    if authorization.decision_fingerprint != _decision_fingerprint(
        fingerprint,
        authorization.run_id,
        authorization.library_root_id,
        authorization.selections,
    ):
        return "authorization selections changed after the explicit decision"
    try:
        authorize_ingestion(plan, authorization.selections)
    except IngestionAuthorizationError as error:
        return str(error)
    return None


def _decision_fingerprint(
    fingerprint: str,
    run_id: str,
    root_id: str,
    selections: tuple[CandidateSelection, ...],
) -> str:
    payload = {
        "plan": fingerprint,
        "run_id": run_id,
        "root_id": root_id,
        "selections": [
            [
                item.candidate.run_id,
                item.candidate.library_root_id,
                item.candidate.relative_path,
                str(item.asset_kind),
                item.media_type,
            ]
            for item in selections
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _non_applied_items(
    plan: CatalogChangePlan,
    selected: object,
    selected_disposition: IngestionItemDisposition,
) -> tuple[IngestionItemResult, ...]:
    selected_paths = set(selected) if isinstance(selected, dict) else set()
    results: list[IngestionItemResult] = []
    for item in plan.changes:
        reference = candidate_reference(plan, item.relative_path)
        if item.classification is ChangeClassification.KNOWN_LOCATION_OBSERVED:
            results.append(
                IngestionItemResult(
                    reference,
                    IngestionItemDisposition.ALREADY_EXISTS,
                    item.asset_id,
                    item.location_id,
                )
            )
        elif item.classification is ChangeClassification.NEW_FILE_CANDIDATE:
            results.append(
                IngestionItemResult(
                    reference,
                    (
                        selected_disposition
                        if item.relative_path in selected_paths or not selected_paths
                        else IngestionItemDisposition.IGNORED_NOT_AUTHORIZED
                    ),
                )
            )
    return tuple(results)


def _plan_items(
    plan: CatalogChangePlan,
    disposition: IngestionItemDisposition,
    diagnostic: str,
) -> tuple[IngestionItemResult, ...]:
    return tuple(
        IngestionItemResult(
            candidate_reference(plan, item.relative_path), disposition, diagnostic=diagnostic
        )
        for item in plan.changes
    )


def _physical_identity_text(identity: PhysicalIdentity | None) -> str | None:
    return None if identity is None else f"scanner:{identity.device}:{identity.file_id}"


def _rollback_failed(error: BaseException) -> bool:
    return any("rollback also failed" in note for note in getattr(error, "__notes__", ()))


def _path_in_scope(path: str, scope: ScanScope) -> bool:
    inside = scope.relative_path == "." or path.startswith(f"{scope.relative_path}/")
    if not inside:
        return False
    return scope.recursive or PurePosixPath(path).parent.as_posix() == scope.relative_path
