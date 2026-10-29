"""Session-only synthetic presentation. No detector, planner, or filesystem access."""

from __future__ import annotations

import base64
import binascii
import copy
import json
import sqlite3
from uuid import UUID, uuid4, uuid5

from playmemories_photo_manager.duplicates.models import (
    DuplicateBlockKind as Block,
)
from playmemories_photo_manager.duplicates.models import (
    DuplicateCoverage as Coverage,
)
from playmemories_photo_manager.duplicates.models import (
    DuplicateDecisionStatus as Decision,
)
from playmemories_photo_manager.duplicates.models import (
    DuplicateIssueKind as Issue,
)
from playmemories_photo_manager.duplicates.models import (
    DuplicatePlanState as Plan,
)

ORDER = "sha256-size/root-name-relative-location-v1"
MAX_RESPONSE_BYTES = 240 * 1024  # Leaves room for the authenticated response envelope.


class PresentationError(ValueError):
    """A fixed public error code, never caller text or filesystem information."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _encode(value: object) -> str:
    return base64.urlsafe_b64encode(_canonical(value)).decode().rstrip("=")


def _decode(text: object) -> dict:
    try:
        if not isinstance(text, str) or not 1 <= len(text) <= 2048:
            raise ValueError
        value = json.loads(
            base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)
        )
        if not isinstance(value, dict) or _encode(value) != text:
            raise ValueError
        return value
    except (ValueError, TypeError, binascii.Error, UnicodeError, RecursionError):
        raise PresentationError("invalid_request") from None


def synthetic_groups(connection: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    """Reuse catalog IDs; extra occurrences live ONLY in this simulated read model."""
    rows = connection.execute(
        """SELECT l.id, l.asset_id, l.library_root_id, l.normalized_relative_path,
                  r.display_name
           FROM file_location l JOIN library_root r ON r.id = l.library_root_id
           ORDER BY l.id"""
    ).fetchall()
    members = [
        dict(
            location_id=row[0],
            asset_id=row[1],
            library_root_id=row[2],
            relative_path=row[3],
            root_display_name=row[4],
            location_source="catalog_fixture",
            hardlinked=False,
            identity_conflict=False,
            protected=None,
            blocks=[],
        )
        for row in rows
    ]
    groups = []
    # Disjoint occurrences; the large group proves that D02C's 100-location cap
    # cannot be used as the duplicate membership inventory.
    partitions = [members[:2], members[2:4], members[4:6], members[6:]]
    for index, group_members in enumerate(partitions):
        if not group_members:
            continue
        if index == 1:
            extra = dict(group_members[0])
            extra.update(
                location_id=str(uuid5(UUID(extra["asset_id"]), "d03-hardlink")),
                relative_path="Demonstração/ação <b>literal</b>/atalho-sintético.jpg",
                location_source="projection_fixture",
            )
            group_members.append(extra)
            for member in (group_members[0], extra):
                member.update(hardlinked=True, blocks=[Block.HARDLINK])
        if index == 2:
            for member in group_members:
                member.update(identity_conflict=True, blocks=[Block.IDENTITY_CONFLICT])
        if index == 3:
            seed = group_members[0]
            for number in range(105 - len(group_members)):
                extra = dict(seed)
                extra.update(
                    location_id=str(uuid5(UUID(seed["asset_id"]), f"d03-copy-{number}")),
                    relative_path=f"Cópias simuladas/{'álbum longo ' * 8}/cópia-{number:03}.jpg",
                    location_source="projection_fixture",
                )
                group_members.append(extra)
            group_members[0].update(protected=True, blocks=[Block.PROTECTED])
        group_members.sort(
            key=lambda m: (m["root_display_name"], m["relative_path"], m["location_id"])
        )
        digest = f"{index + 1:064x}"  # Simulated, deliberately NOT calculated from media.
        size = str(2**53 + 1 if index == 3 else 2048 * (index + 1))
        blocks = sorted(
            {b for m in group_members for b in m["blocks"]} | {Block.INCOMPLETE_COVERAGE}
        )
        groups.append(
            dict(
                group_key=f"{digest}:{size}",
                sha256=digest,
                byte_size=size,
                evidence_fingerprint=None,
                occurrence_count=len(group_members),
                physical_copy_count=len(group_members) - (1 if index == 1 else 0),
                blocks=blocks,
                plan_state=Plan.STALE if index == 2 else None,
                review=dict(
                    decision_id=str(uuid5(UUID(group_members[0]["asset_id"]), "d03-review")),
                    status=Decision.STALE,
                    keep_location_id=group_members[0]["location_id"],
                    reason="Escolha histórica simulada <script>literal</script>; sem revalidação.",
                )
                if index == 2
                else None,
                members=group_members,
            )
        )
    issues = [
        dict(
            kind=Issue.ROOT_OFFLINE,
            asset_id=m["asset_id"],
            location_id=m["location_id"],
            library_root_id=m["library_root_id"],
            relative_path=m["relative_path"],
        )
        for m in members[:1]
    ]
    return groups, issues


class DuplicatePresentation:
    """A read model bound to one bridge session, never a persisted analysis."""

    def __init__(
        self,
        groups: list[dict],
        issues: list[dict],
        *,
        coverage: Coverage = Coverage.PARTIAL,
        snapshot_id: str | None = None,
    ) -> None:
        self.groups = copy.deepcopy(groups)
        self.issues = copy.deepcopy(issues)
        self.coverage = coverage
        self.snapshot_id = snapshot_id or str(uuid4())

    def request(self, method: str, params: object) -> dict:
        try:
            return self._request(method, params)
        except PresentationError as error:
            return {"status": str(error)}

    def _request(self, method: str, params: object) -> dict:
        group_method = method == "duplicates.group"
        allowed = {"page_size", "after"} | ({"snapshot_id", "group_key"} if group_method else set())
        if not isinstance(params, dict) or set(params) - allowed:
            raise PresentationError("invalid_request")
        size = params.get("page_size", 24)
        if type(size) is not int or not 1 <= size <= 50:
            raise PresentationError("invalid_request")
        group_key = params.get("group_key") if group_method else None
        if group_method:
            if not isinstance(group_key, str) or not isinstance(params.get("snapshot_id"), str):
                raise PresentationError("invalid_request")
            if params["snapshot_id"] != self.snapshot_id:
                raise PresentationError("stale_snapshot")
        offset = 0
        if params.get("after") is not None:
            cursor = _decode(params["after"])
            if set(cursor) != {"v", "snapshot", "order", "group", "offset"}:
                raise PresentationError("invalid_request")
            if type(cursor["v"]) is not int or cursor["v"] != 1 or cursor["order"] != ORDER:
                raise PresentationError("invalid_request")
            if cursor["snapshot"] != self.snapshot_id:
                raise PresentationError("stale_snapshot")
            if (
                cursor["group"] != group_key
                or type(cursor["offset"]) is not int
                or cursor["offset"] < 1
            ):
                raise PresentationError("invalid_request")
            offset = cursor["offset"]
        group = next((g for g in self.groups if g["group_key"] == group_key), None)
        if group_method and group is None:
            raise PresentationError("not_found")
        items = group["members"] if group is not None else self.groups
        if offset and offset >= len(items):
            raise PresentationError("invalid_request")
        end = min(offset + size, len(items))
        page = dict(
            version=1,
            snapshot_id=self.snapshot_id,
            source="synthetic_fixture",
            observed_at=None,
            freshness="synthetic",
            coverage=self.coverage,
            issues=self.issues,
            eligible_location_count=sum(g["occurrence_count"] for g in self.groups),
            hashed_location_count=0,
            total_count=len(items),
            next_cursor=_encode(
                dict(v=1, snapshot=self.snapshot_id, order=ORDER, group=group_key, offset=end)
            )
            if end < len(items)
            else None,
        )
        if group is None:
            page["groups"] = [
                {k: v for k, v in g.items() if k != "members"} for g in items[offset:end]
            ]
        else:
            page["group"] = {k: v for k, v in group.items() if k != "members"}
            page["members"] = items[offset:end]

        # byte_size is always decimal text; every JSON number must be JS-exact.
        def check_numbers(value: object) -> None:
            if type(value) is int and abs(value) > 2**53 - 1:
                raise PresentationError("internal_error")
            if isinstance(value, dict):
                for item in value.values():
                    check_numbers(item)
            elif isinstance(value, list):
                for item in value:
                    check_numbers(item)

        check_numbers(page)
        result = {"status": "ready", "page": page}
        if len(_canonical(result)) > MAX_RESPONSE_BYTES:
            raise PresentationError("response_too_large")
        return result


def validate_unavailable(method: str, params: object) -> dict:
    """Validate the same narrow input even without a snapshot; no catalog query."""
    validator = DuplicatePresentation(
        [], [], coverage=Coverage.UNAVAILABLE, snapshot_id="unavailable"
    )
    result = validator.request(method, params)
    if result["status"] == "invalid_request":
        return result
    return {"status": "analysis_not_available"}
