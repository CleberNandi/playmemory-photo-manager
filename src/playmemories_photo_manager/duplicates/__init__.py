"""Internal exact-duplicate read model."""

from .detector import find_exact_duplicates
from .models import (
    DuplicateCoverage,
    DuplicateIssue,
    DuplicateIssueKind,
    DuplicateMember,
    ExactDuplicateGroup,
    ExactDuplicateResult,
)

__all__ = [
    "DuplicateCoverage",
    "DuplicateIssue",
    "DuplicateIssueKind",
    "DuplicateMember",
    "ExactDuplicateGroup",
    "ExactDuplicateResult",
    "find_exact_duplicates",
]
