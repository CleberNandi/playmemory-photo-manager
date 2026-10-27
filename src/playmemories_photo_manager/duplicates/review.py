"""Persisted human review and non-executable plans for exact duplicates."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

from .detector import find_exact_duplicates
from .models import (
    DuplicateBlockKind,
    DuplicateCoverage,
    DuplicateDecisionStatus,
    DuplicateMember,
    DuplicatePlanGroup,
    DuplicatePlanMember,
    DuplicatePlanState,
    ExactDuplicateDecision,
    ExactDuplicateGroup,
    ExactDuplicatePlan,
)


class DuplicateReviewError(ValueError):
    """The requested review cannot be recorded safely."""


def save_exact_duplicate_decision(
    connection: sqlite3.Connection,
    *,
    sha256: str,
    keep_location_id: str,
    reason: str,
) -> ExactDuplicateDecision:
    """Re-detect a group and atomically persist an explicit human keep decision."""
    reason = reason.strip()
    if not reason:
        raise DuplicateReviewError("reason must not be empty")
    result = find_exact_duplicates(connection)
    group = next((item for item in result.groups if item.sha256 == sha256), None)
    if group is None:
        raise DuplicateReviewError("exact duplicate group is not currently verifiable")
    if keep_location_id not in {member.location_id for member in group.members}:
        raise DuplicateReviewError("keep location is not a member of the verified group")

    fingerprint = evidence_fingerprint(group.members)
    identifier = str(uuid.uuid4())
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """UPDATE exact_duplicate_decision
            SET status = 'stale', stale_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE sha256 = ? AND byte_size = ? AND status = 'current'""",
            (group.sha256, group.byte_size),
        )
        connection.execute(
            """INSERT INTO exact_duplicate_decision(
                id, sha256, byte_size, keep_location_id, reason, evidence_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (identifier, group.sha256, group.byte_size, keep_location_id, reason, fingerprint),
        )
        connection.executemany(
            """INSERT INTO exact_duplicate_decision_member(
                decision_id, location_id, asset_id, library_root_id, relative_path,
                byte_size, sha256, device, file_id, link_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    identifier,
                    member.location_id,
                    member.asset_id,
                    member.library_root_id,
                    member.relative_path,
                    member.byte_size,
                    member.sha256,
                    member.device,
                    member.file_id,
                    member.link_count,
                )
                for member in group.members
            ],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return ExactDuplicateDecision(
        identifier,
        group.sha256,
        group.byte_size,
        keep_location_id,
        reason,
        fingerprint,
        DuplicateDecisionStatus.CURRENT,
        group.members,
    )


def generate_exact_duplicate_plan(connection: sqlite3.Connection) -> ExactDuplicatePlan:
    """Revalidate physical evidence and return a deterministic, consultative plan."""
    result = find_exact_duplicates(connection)
    decisions = _review_decisions(connection)
    current_groups = {(group.sha256, group.byte_size): group for group in result.groups}
    stale_ids: list[str] = []
    planned: list[DuplicatePlanGroup] = []

    for key in sorted(set(current_groups) | set(decisions)):
        group = current_groups.get(key)
        decision = decisions.get(key)
        if decision is not None and (
            decision.status is DuplicateDecisionStatus.STALE
            or group is None
            or decision.evidence_fingerprint != evidence_fingerprint(group.members)
            or decision.keep_location_id not in {member.location_id for member in group.members}
        ):
            stale_ids.append(decision.id)
            planned.append(_stale_group(decision))
            continue
        if group is None:  # pragma: no cover - only possible for an inconsistent query snapshot
            continue
        planned.append(_plan_group(connection, group, decision, result.coverage))

    if stale_ids:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.executemany(
                """UPDATE exact_duplicate_decision
                SET status = 'stale', stale_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ? AND status = 'current'""",
                [(identifier,) for identifier in stale_ids],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return ExactDuplicatePlan(tuple(planned), result.coverage, result.issues)


def evidence_fingerprint(members: tuple[DuplicateMember, ...]) -> str:
    """Fingerprint the complete, ordered physical and catalog evidence for a group."""
    payload = [
        {
            "asset_id": member.asset_id,
            "byte_size": member.byte_size,
            "device": member.device,
            "file_id": member.file_id,
            "library_root_id": member.library_root_id,
            "link_count": member.link_count,
            "location_id": member.location_id,
            "relative_path": member.relative_path,
            "sha256": member.sha256,
        }
        for member in members
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _review_decisions(
    connection: sqlite3.Connection,
) -> dict[tuple[str, int], ExactDuplicateDecision]:
    rows = connection.execute(
        """SELECT id, sha256, byte_size, keep_location_id, reason, evidence_fingerprint, status
        FROM exact_duplicate_decision
        ORDER BY sha256, byte_size, status = 'current' DESC, created_at DESC, id DESC"""
    ).fetchall()
    decisions: dict[tuple[str, int], ExactDuplicateDecision] = {}
    for row in rows:
        key = (row["sha256"], row["byte_size"])
        decisions.setdefault(
            key,
            ExactDuplicateDecision(
                id=row["id"],
                sha256=row["sha256"],
                byte_size=row["byte_size"],
                keep_location_id=row["keep_location_id"],
                reason=row["reason"],
                evidence_fingerprint=row["evidence_fingerprint"],
                status=DuplicateDecisionStatus(row["status"]),
                members=_decision_members(connection, row["id"]),
            ),
        )
    return decisions


def _decision_members(
    connection: sqlite3.Connection, decision_id: str
) -> tuple[DuplicateMember, ...]:
    rows = connection.execute(
        """SELECT asset_id, location_id, library_root_id, relative_path, byte_size,
            sha256, device, file_id, link_count
        FROM exact_duplicate_decision_member WHERE decision_id = ?
        ORDER BY library_root_id, relative_path, location_id, asset_id""",
        (decision_id,),
    ).fetchall()
    return tuple(DuplicateMember(**dict(row)) for row in rows)


def _plan_group(
    connection: sqlite3.Connection,
    group: ExactDuplicateGroup,
    decision: ExactDuplicateDecision | None,
    coverage: DuplicateCoverage,
) -> DuplicatePlanGroup:
    protected = _protected_assets(connection, {member.asset_id for member in group.members})
    blocks: set[DuplicateBlockKind] = set()
    if coverage is not DuplicateCoverage.COMPLETE:
        blocks.add(DuplicateBlockKind.INCOMPLETE_COVERAGE)
    identities: dict[tuple[int, int], set[str]] = {}
    for member in group.members:
        identities.setdefault(member.physical_identity, set()).add(member.asset_id)
        if member.is_hardlinked:
            blocks.add(DuplicateBlockKind.HARDLINK)
    if any(len(asset_ids) > 1 for asset_ids in identities.values()):
        blocks.add(DuplicateBlockKind.IDENTITY_CONFLICT)

    keep_id = decision.keep_location_id if decision else None
    members = tuple(
        DuplicatePlanMember(
            member=member,
            keep=member.location_id == keep_id,
            candidate=keep_id is not None and member.location_id != keep_id,
            protected=member.asset_id in protected,
            hardlinked=member.is_hardlinked,
        )
        for member in group.members
    )
    if any(item.candidate and item.protected for item in members):
        blocks.add(DuplicateBlockKind.PROTECTED)
    if decision is not None and sum(item.keep for item in members) != 1:
        blocks.add(DuplicateBlockKind.PRESERVED_COPY_UNVERIFIED)
    state = DuplicatePlanState.PENDING
    if decision is not None:
        state = DuplicatePlanState.BLOCKED if blocks else DuplicatePlanState.READY
    return DuplicatePlanGroup(
        group.sha256,
        group.byte_size,
        state,
        decision.id if decision else None,
        decision.reason if decision else None,
        members,
        tuple(sorted(blocks)),
    )


def _protected_assets(connection: sqlite3.Connection, asset_ids: set[str]) -> set[str]:
    if not asset_ids:
        return set()
    placeholders = ",".join("?" for _ in asset_ids)
    ordered = tuple(sorted(asset_ids))
    queries = (
        f"SELECT asset_id FROM album_asset WHERE asset_id IN ({placeholders})",
        f"SELECT asset_id FROM asset_tag WHERE asset_id IN ({placeholders})",
        f"SELECT asset_id FROM user_annotation WHERE asset_id IN ({placeholders})",
        f"SELECT asset_id FROM metadata WHERE asset_id IN ({placeholders})",
        f"SELECT asset_id FROM thumbnail WHERE asset_id IN ({placeholders})",
    )
    protected: set[str] = set()
    for query in queries:
        protected.update(row[0] for row in connection.execute(query, ordered))
    return protected


def _stale_group(decision: ExactDuplicateDecision) -> DuplicatePlanGroup:
    members = tuple(
        DuplicatePlanMember(
            member=member,
            keep=member.location_id == decision.keep_location_id,
            candidate=member.location_id != decision.keep_location_id,
            protected=False,
            hardlinked=member.is_hardlinked,
        )
        for member in decision.members
    )
    return DuplicatePlanGroup(
        decision.sha256,
        decision.byte_size,
        DuplicatePlanState.STALE,
        decision.id,
        decision.reason,
        members,
        (DuplicateBlockKind.PRESERVED_COPY_UNVERIFIED,),
    )
