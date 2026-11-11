"""Explicit in-memory consent for a validated catalogable selection, without writes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ..catalog import AssetKind
from .images import FORMATS
from .models import CandidateSelection, IngestionAuthorizationError
from .scoping import ScopedIngestionProposal, scope_catalogable_proposal

MAX_AUTHORIZED_CANDIDATES = 100


@dataclass(frozen=True, slots=True)
class ScopedIngestionAuthorization:
    scope_fingerprint: str
    run_id: str
    library_root_id: str
    candidate_ids: tuple[str, ...]
    selections: tuple[CandidateSelection, ...]
    decision_fingerprint: str


def authorize_scoped_ingestion(
    scoped: ScopedIngestionProposal, candidate_ids: tuple[str, ...]
) -> ScopedIngestionAuthorization:
    """Bind exact opaque IDs to trusted JPEG evidence; no filesystem or SQLite access.

    An empty choice is explicit and creates no selections. This is a private backend
    decision object, not a signed credential or a renderer-supplied authorization.
    """
    if not isinstance(scoped, ScopedIngestionProposal):
        raise IngestionAuthorizationError("scoped proposal is required")
    rebuilt = scope_catalogable_proposal(
        scoped.original, scoped.eligibilities, additions_only=scoped.additions_only
    )
    if rebuilt != scoped:
        raise IngestionAuthorizationError("scoped proposal has changed")
    if (
        not isinstance(candidate_ids, tuple)
        or len(candidate_ids) > MAX_AUTHORIZED_CANDIDATES
        or any(not isinstance(identifier, str) for identifier in candidate_ids)
        or len(set(candidate_ids)) != len(candidate_ids)
    ):
        raise IngestionAuthorizationError("selection must contain up to 100 unique opaque IDs")
    eligible = set(rebuilt.eligible_candidates)
    by_id = {
        item.candidate_id: item
        for item in rebuilt.eligibilities
        if item.candidate in eligible and item.state == "eligible"
    }
    if any(identifier not in by_id for identifier in candidate_ids):
        raise IngestionAuthorizationError("selection is not eligible in this proposal")
    ordered = tuple(
        sorted(candidate_ids, key=lambda identifier: by_id[identifier].candidate.relative_path)
    )
    selections = tuple(
        CandidateSelection(
            by_id[identifier].candidate,
            AssetKind.PHOTO,
            FORMATS[by_id[identifier].detected_format][0],
        )
        for identifier in ordered
    )
    run_id = rebuilt.original.scan_result.run_id
    root_id = rebuilt.original.plan.library_root_id
    content = {
        "version": 1,
        "scope_fingerprint": rebuilt.scope_fingerprint,
        "run_id": run_id,
        "library_root_id": root_id,
        "selections": [
            {
                "candidate_id": identifier,
                "relative_path": selection.candidate.relative_path,
                "asset_kind": selection.asset_kind.value,
                "media_type": selection.media_type,
            }
            for identifier, selection in zip(ordered, selections, strict=True)
        ],
    }
    decision = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ScopedIngestionAuthorization(
        rebuilt.scope_fingerprint, run_id, root_id, ordered, selections, decision
    )


def validate_scoped_authorization(
    scoped: ScopedIngestionProposal, authorization: ScopedIngestionAuthorization
) -> None:
    """Rebuild and compare consent before a future caller admits any write operation.

    This does not revalidate physical freshness, grant validity, or SQLite state.
    Those remain mandatory at application, which is not implemented here.
    """
    if not isinstance(authorization, ScopedIngestionAuthorization):
        raise IngestionAuthorizationError("scoped authorization is required")
    expected = authorize_scoped_ingestion(scoped, authorization.candidate_ids)
    if expected != authorization:
        raise IngestionAuthorizationError("authorization does not match the reviewed selection")
