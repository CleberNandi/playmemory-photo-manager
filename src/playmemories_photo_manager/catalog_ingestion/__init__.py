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
    prepare_ingestion,
)

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
    "apply_ingestion",
    "authorize_ingestion",
    "candidate_reference",
    "plan_fingerprint",
    "prepare_ingestion",
]
