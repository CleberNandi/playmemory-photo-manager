"""Atomic scoped ingestion. Session, grants and command deduplication belong to the adapter."""

from __future__ import annotations

from collections.abc import Callable

from ..catalog import Catalog, CatalogError
from ..catalog.errors import CatalogStateConflictError, NotFoundError
from ..catalog.models import NewFileRegistration
from ..library import LibraryError
from .models import (
    IngestionAuthorizationError,
    IngestionBatchStatus,
    IngestionItemDisposition,
    IngestionItemResult,
    IngestionReport,
)
from .scoped_authorization import ScopedIngestionAuthorization, validate_scoped_authorization
from .scoped_preflight import ScopedPreflightError, preflight_scoped_ingestion
from .scoping import ProposalResourceLimitError, ScopedIngestionProposal, scope_catalogable_proposal
from .service import _physical_identity_text, prepare_from_snapshot
from .snapshot import SnapshotLimits, SnapshotResourceLimitError, _capture_connection_snapshot


def _uncertain(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if any(
            "rollback also failed" in note or "commit outcome unknown" in note
            for note in getattr(error, "__notes__", ())
        ):
            return True
        error = error.__cause__ or error.__context__
    return False


def apply_scoped_ingestion(
    catalog: Catalog,
    scoped: ScopedIngestionProposal,
    authorization: ScopedIngestionAuthorization | None,
    *,
    expected_root_mount: int,
    cancellation_requested: Callable[[], bool] | None = None,
) -> IngestionReport:
    """Reverify media outside SQLite, then replan and commit the exact choice atomically.

    Catalog must own an idle command connection from the active library session.
    Unknown commit/rollback outcome closes that connection; the adapter must suspend
    commands and recover explicitly, never retry admission automatically.
    """
    if not isinstance(catalog, Catalog) or not isinstance(scoped, ScopedIngestionProposal):
        raise IngestionAuthorizationError("catalog and scoped proposal are required")
    # Validate even a no-op, without consulting filesystem or starting a transaction.
    rebuilt = scope_catalogable_proposal(scoped.original, scoped.eligibilities)
    if rebuilt != scoped:
        raise IngestionAuthorizationError("scoped proposal has changed")
    selected = set()
    results = {}

    def report(status, disposition=IngestionItemDisposition.BLOCKED, diagnostic=None):
        items = []
        for candidate in scoped.eligible_candidates:
            persisted = results.get(candidate.relative_path)
            items.append(
                IngestionItemResult(
                    candidate,
                    IngestionItemDisposition.CREATED
                    if persisted is not None
                    else disposition
                    if candidate.relative_path in selected
                    else IngestionItemDisposition.IGNORED_NOT_AUTHORIZED,
                    persisted.asset.id if persisted is not None else None,
                    persisted.location.id if persisted is not None else None,
                )
            )
        return IngestionReport(
            scoped.original.plan.run_id,
            scoped.original.plan.library_root_id,
            scoped.scope_fingerprint,
            status,
            tuple(items),
            diagnostic,
        )

    if authorization is None:
        return report(IngestionBatchStatus.NO_AUTHORIZATION, diagnostic="no_authorization")
    try:
        validate_scoped_authorization(scoped, authorization)
    except IngestionAuthorizationError:
        return report(IngestionBatchStatus.REJECTED, diagnostic="invalid_authorization")
    selected = {item.candidate.relative_path for item in authorization.selections}
    if not selected:
        return report(IngestionBatchStatus.EMPTY_SELECTION)
    if catalog._connection.in_transaction:
        return report(IngestionBatchStatus.REJECTED, diagnostic="active_transaction")
    by_path = {item.candidate.relative_path: item for item in scoped.eligibilities}
    registrations = tuple(
        NewFileRegistration(
            relative_path=selection.candidate.relative_path,
            kind=selection.asset_kind,
            byte_size=by_path[selection.candidate.relative_path].observation.byte_size,
            media_type=selection.media_type,
            filesystem_id=_physical_identity_text(
                by_path[selection.candidate.relative_path].observation.physical_identity
            ),
            observed_mtime_ns=by_path[
                selection.candidate.relative_path
            ].observation.timestamps.modified_ns,
        )
        for selection in authorization.selections
    )
    if any(
        item.observed_mtime_ns is not None and item.observed_mtime_ns < 0 for item in registrations
    ):
        return report(IngestionBatchStatus.REJECTED, diagnostic="invalid_observation")
    try:
        with preflight_scoped_ingestion(
            scoped,
            authorization,
            expected_root_mount=expected_root_mount,
            cancellation_requested=cancellation_requested,
        ) as physical:

            def validate_current():
                physical.check_root()
                current_snapshot = _capture_connection_snapshot(
                    catalog._connection,
                    scoped.original.plan.library_root_id,
                    SnapshotLimits(),
                )
                current = prepare_from_snapshot(
                    current_snapshot,
                    scoped.original.scan_result,
                    scoped.original.planning_context,
                )
                current_scope = scope_catalogable_proposal(current, scoped.eligibilities)
                if current_scope != scoped:
                    raise CatalogStateConflictError("catalog changed", relative_paths=())
                validate_scoped_authorization(current_scope, authorization)
                physical.check_root()

            persisted = catalog._register_new_files_atomically(
                scoped.original.plan.library_root_id,
                scoped.original.scan_result.root.absolute_path,
                registrations,
                before_write=validate_current,
            )
        # Publish IDs only after commit has returned, never from a partially written batch.
        results = {item.location.normalized_relative_path: item for item in persisted}
        return report(IngestionBatchStatus.APPLIED)
    except (
        CatalogError,
        LibraryError,
        ScopedPreflightError,
        IngestionAuthorizationError,
        SnapshotResourceLimitError,
        ProposalResourceLimitError,
    ) as error:
        if _uncertain(error):
            catalog._connection.close()
            return report(
                IngestionBatchStatus.TRANSACTION_FAILED,
                IngestionItemDisposition.TRANSACTION_FAILED,
                "outcome_unknown",
            )
        if isinstance(error, (CatalogStateConflictError, NotFoundError)):
            return report(
                IngestionBatchStatus.CONFLICT, IngestionItemDisposition.CONFLICT, "catalog_changed"
            )
        if isinstance(error, ScopedPreflightError):
            return report(IngestionBatchStatus.REJECTED, diagnostic=str(error))
        if isinstance(error, (SnapshotResourceLimitError, ProposalResourceLimitError)):
            return report(IngestionBatchStatus.REJECTED, diagnostic="resource_limit")
        if isinstance(error, IngestionAuthorizationError):
            return report(
                IngestionBatchStatus.CONFLICT, IngestionItemDisposition.CONFLICT, "catalog_changed"
            )
        return report(
            IngestionBatchStatus.TRANSACTION_FAILED,
            IngestionItemDisposition.TRANSACTION_FAILED,
            "transaction_failed",
        )
    except Exception as error:
        if not _uncertain(error):
            raise
        catalog._connection.close()
        return report(
            IngestionBatchStatus.TRANSACTION_FAILED,
            IngestionItemDisposition.TRANSACTION_FAILED,
            "outcome_unknown",
        )
