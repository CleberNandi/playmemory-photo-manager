"""Internal exact-duplicate read model."""

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


# Presentation consumers can reuse enums without loading physical analysis code.
def __getattr__(name: str):
    if name == "find_exact_duplicates":
        from .detector import find_exact_duplicates

        return find_exact_duplicates
    if name in {
        "DuplicateReviewError",
        "evidence_fingerprint",
        "generate_exact_duplicate_plan",
        "save_exact_duplicate_decision",
    }:
        from . import review

        return getattr(review, name)
    raise AttributeError(name)


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
