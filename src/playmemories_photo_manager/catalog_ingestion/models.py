"""Contracts for explicitly authorized catalog ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from playmemories_photo_manager.catalog import AssetKind
from playmemories_photo_manager.change_planning import (
    CatalogChangePlan,
    CatalogSnapshot,
    PlanningContext,
)
from playmemories_photo_manager.evidence import EvidenceAssessment
from playmemories_photo_manager.scanner import ScanResult


class IngestionBatchStatus(StrEnum):
    APPLIED = "applied"
    NO_AUTHORIZATION = "no_authorization"
    EMPTY_SELECTION = "empty_selection"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    TRANSACTION_FAILED = "transaction_failed"


class IngestionItemDisposition(StrEnum):
    CREATED = "created"
    ALREADY_EXISTS = "already_exists"
    IGNORED_NOT_AUTHORIZED = "ignored_not_authorized"
    BLOCKED = "blocked"
    CONFLICT = "conflict"
    TRANSACTION_FAILED = "transaction_failed"


@dataclass(frozen=True, slots=True)
class CandidateReference:
    run_id: str
    library_root_id: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    candidate: CandidateReference
    asset_kind: AssetKind
    media_type: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionAuthorization:
    plan_fingerprint: str
    run_id: str
    library_root_id: str
    selections: tuple[CandidateSelection, ...]
    decision_fingerprint: str


@dataclass(frozen=True, slots=True)
class IngestionProposal:
    scan_result: ScanResult
    assessment: EvidenceAssessment
    catalog_snapshot: CatalogSnapshot
    planning_context: PlanningContext
    plan: CatalogChangePlan


@dataclass(frozen=True, slots=True)
class IngestionItemResult:
    candidate: CandidateReference
    disposition: IngestionItemDisposition
    asset_id: str | None = None
    location_id: str | None = None
    diagnostic: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionReport:
    run_id: str
    library_root_id: str
    plan_fingerprint: str
    status: IngestionBatchStatus
    items: tuple[IngestionItemResult, ...]
    diagnostic: str | None = None


class IngestionAuthorizationError(ValueError):
    """The requested authorization does not match an applicable plan candidate."""
