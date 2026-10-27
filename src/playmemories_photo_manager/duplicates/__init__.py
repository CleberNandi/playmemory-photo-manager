"""Internal exact-duplicate read model."""

from .detector import find_exact_duplicates
from .models import (
    DuplicateBlockKind,
    DuplicateCoverage,
    DuplicateDecisionStatus,
    DuplicateIssue,
    DuplicateIssueKind,
    DuplicateMember,
    DuplicatePlanGroup,
    DuplicatePlanMember,
    DuplicatePlanState,
    ExactDuplicateDecision,
    ExactDuplicateGroup,
    ExactDuplicatePlan,
    ExactDuplicateResult,
)
from .review import (
    DuplicateReviewError,
    evidence_fingerprint,
    generate_exact_duplicate_plan,
    save_exact_duplicate_decision,
)

__all__ = [
    "DuplicateBlockKind",
    "DuplicateCoverage",
    "DuplicateDecisionStatus",
    "DuplicateIssue",
    "DuplicateIssueKind",
    "DuplicateMember",
    "DuplicatePlanGroup",
    "DuplicatePlanMember",
    "DuplicatePlanState",
    "DuplicateReviewError",
    "ExactDuplicateDecision",
    "ExactDuplicateGroup",
    "ExactDuplicatePlan",
    "ExactDuplicateResult",
    "evidence_fingerprint",
    "find_exact_duplicates",
    "generate_exact_duplicate_plan",
    "save_exact_duplicate_decision",
]
