"""Controlled vertical catalog-ingestion API."""

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
from .service import (
    apply_ingestion,
    authorize_ingestion,
    candidate_reference,
    plan_fingerprint,
    prepare_from_snapshot,
    prepare_ingestion,
)
from .snapshot import SnapshotLimits, SnapshotResourceLimitError, capture_catalog_snapshot

__all__ = [
    "CandidateReference",
    "CandidateSelection",
    "IngestionAuthorization",
    "IngestionAuthorizationError",
    "IngestionBatchStatus",
    "IngestionItemDisposition",
    "IngestionItemResult",
    "IngestionProposal",
    "IngestionReport",
    "SnapshotLimits",
    "SnapshotResourceLimitError",
    "apply_ingestion",
    "authorize_ingestion",
    "candidate_reference",
    "capture_catalog_snapshot",
    "plan_fingerprint",
    "prepare_from_snapshot",
    "prepare_ingestion",
]
