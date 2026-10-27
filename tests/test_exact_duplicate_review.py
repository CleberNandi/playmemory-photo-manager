from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from pathlib import Path

import pytest

from playmemories_photo_manager.duplicates import (
    DuplicateBlockKind,
    DuplicateCoverage,
    DuplicatePlanState,
    DuplicateReviewError,
    generate_exact_duplicate_plan,
    save_exact_duplicate_decision,
)


def _id() -> str:
    return str(uuid.uuid4())


def _group(database: sqlite3.Connection, root: Path, names=("one.jpg", "two.jpg")):
    root_id = _id()
    database.execute(
        "INSERT INTO library_root(id, display_name, normalized_path) VALUES (?, 'Review', ?)",
        (root_id, str(root)),
    )
    members = []
    for name in names:
        path = root / name
        path.write_bytes(b"same bytes")
        info = path.stat()
        asset_id, location_id = _id(), _id()
        database.execute("INSERT INTO asset(id, kind) VALUES (?, 'photo')", (asset_id,))
        database.execute(
            """INSERT INTO file_location(
                id, asset_id, library_root_id, normalized_relative_path, filesystem_id,
                observed_byte_size, observed_mtime_ns
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                location_id,
                asset_id,
                root_id,
                name,
                f"scanner:{info.st_dev}:{info.st_ino}",
                info.st_size,
                info.st_mtime_ns,
            ),
        )
        members.append((asset_id, location_id, path))
    return hashlib.sha256(b"same bytes").hexdigest(), members


def test_decision_persists_reason_members_and_evidence_fingerprint(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path)

    decision = save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[0][1], reason="Best provenance"
    )

    row = database.execute("SELECT * FROM exact_duplicate_decision").fetchone()
    assert row["id"] == decision.id
    assert row["reason"] == "Best provenance"
    assert row["evidence_fingerprint"] == decision.evidence_fingerprint
    persisted = database.execute(
        "SELECT asset_id, location_id FROM exact_duplicate_decision_member ORDER BY location_id"
    ).fetchall()
    assert {tuple(row) for row in persisted} == {
        (asset, location) for asset, location, _ in members
    }


def test_reason_and_verified_member_are_required(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path)

    with pytest.raises(DuplicateReviewError, match="reason"):
        save_exact_duplicate_decision(
            database, sha256=digest, keep_location_id=members[0][1], reason="  "
        )
    with pytest.raises(DuplicateReviewError, match="not a member"):
        save_exact_duplicate_decision(database, sha256=digest, keep_location_id=_id(), reason="x")


def test_plan_is_deterministic_consultative_and_ready_after_revalidation(
    database, tmp_path
) -> None:
    digest, members = _group(database, tmp_path)
    save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[0][1], reason="Keep this occurrence"
    )

    first = generate_exact_duplicate_plan(database)
    second = generate_exact_duplicate_plan(database)

    assert first == second
    assert first.coverage is DuplicateCoverage.COMPLETE
    assert first.action_authorized is False
    assert first.operations_performed is False
    assert first.groups[0].state is DuplicatePlanState.READY
    assert sum(member.keep for member in first.groups[0].members) == 1
    assert sum(member.candidate for member in first.groups[0].members) == 1


def test_changed_bytes_mark_decision_stale_without_deleting_it(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path)
    decision = save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[0][1], reason="Explicit choice"
    )
    members[1][2].write_bytes(b"changed")

    plan = generate_exact_duplicate_plan(database)
    repeated = generate_exact_duplicate_plan(database)

    assert plan.groups[0].state is DuplicatePlanState.STALE
    assert repeated.groups[0].state is DuplicatePlanState.STALE
    row = database.execute(
        "SELECT status, stale_at FROM exact_duplicate_decision WHERE id = ?", (decision.id,)
    ).fetchone()
    assert tuple(row)[0] == "stale"
    assert row["stale_at"] is not None
    assert (
        database.execute(
            "SELECT count(*) FROM exact_duplicate_decision_member WHERE decision_id = ?",
            (decision.id,),
        ).fetchone()[0]
        == 2
    )


def test_stale_decision_can_be_queried_repeatedly_without_writes(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path)
    decision = save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[0][1], reason="Explicit choice"
    )
    members[1][2].write_bytes(b"changed")
    generate_exact_duplicate_plan(database)
    stale_at = database.execute(
        "SELECT stale_at FROM exact_duplicate_decision WHERE id = ?", (decision.id,)
    ).fetchone()[0]
    database_path = database.execute("PRAGMA database_list").fetchone()[2]
    read_only = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    read_only.row_factory = sqlite3.Row
    statements: list[str] = []
    read_only.set_trace_callback(statements.append)
    try:
        first = generate_exact_duplicate_plan(read_only)
        second = generate_exact_duplicate_plan(read_only)
    finally:
        read_only.close()

    assert first == second
    assert first.groups[0].state is DuplicatePlanState.STALE
    assert (
        database.execute(
            "SELECT stale_at FROM exact_duplicate_decision WHERE id = ?", (decision.id,)
        ).fetchone()[0]
        == stale_at
    )
    assert not any(
        statement.lstrip().upper().startswith(("BEGIN", "UPDATE", "COMMIT", "ROLLBACK"))
        for statement in statements
    )


def test_new_decision_preserves_stale_history(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path)
    first = save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[0][1], reason="First"
    )
    second = save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[1][1], reason="Reconsidered"
    )

    rows = database.execute(
        "SELECT id, status FROM exact_duplicate_decision ORDER BY created_at, id"
    ).fetchall()
    assert {tuple(row) for row in rows} == {(first.id, "stale"), (second.id, "current")}


def test_plan_loads_members_only_for_selected_decision(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path)
    save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[0][1], reason="First"
    )
    save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[1][1], reason="Reconsidered"
    )
    statements: list[str] = []
    database.set_trace_callback(statements.append)
    try:
        generate_exact_duplicate_plan(database)
    finally:
        database.set_trace_callback(None)

    member_queries = [
        statement
        for statement in statements
        if "FROM exact_duplicate_decision_member WHERE decision_id" in statement
    ]
    assert len(member_queries) == 1


def test_catalog_dependencies_protect_candidate_and_block_plan(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path)
    album_id = _id()
    database.execute("INSERT INTO album(id, name) VALUES (?, 'Protected')", (album_id,))
    database.execute(
        "INSERT INTO album_asset(album_id, asset_id) VALUES (?, ?)", (album_id, members[1][0])
    )
    save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[0][1], reason="Keep first"
    )

    group = generate_exact_duplicate_plan(database).groups[0]

    assert group.state is DuplicatePlanState.BLOCKED
    assert DuplicateBlockKind.PROTECTED in group.blocks
    assert next(item for item in group.members if item.candidate).protected


@pytest.mark.skipif(os.name != "posix", reason="hardlinks require POSIX semantics")
def test_hardlinks_and_cross_asset_physical_identity_are_blocked(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path)
    members[1][2].unlink()
    os.link(members[0][2], members[1][2])
    info = members[1][2].stat()
    for _asset_id, location_id, _path in members:
        database.execute(
            """UPDATE file_location SET filesystem_id = ?, observed_byte_size = ?,
            observed_mtime_ns = ? WHERE id = ?""",
            (f"scanner:{info.st_dev}:{info.st_ino}", info.st_size, info.st_mtime_ns, location_id),
        )
    save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[0][1], reason="Keep path"
    )

    group = generate_exact_duplicate_plan(database).groups[0]

    assert group.state is DuplicatePlanState.BLOCKED
    assert set(group.blocks) >= {
        DuplicateBlockKind.HARDLINK,
        DuplicateBlockKind.IDENTITY_CONFLICT,
    }


def test_partial_coverage_blocks_otherwise_valid_decision(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path)
    missing_asset = _id()
    database.execute("INSERT INTO asset(id, kind) VALUES (?, 'photo')", (missing_asset,))
    database.execute(
        """INSERT INTO file_location(
            id, asset_id, library_root_id, normalized_relative_path, availability
        ) VALUES (?, ?, (SELECT id FROM library_root LIMIT 1), 'missing.jpg', 'missing')""",
        (_id(), missing_asset),
    )
    save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[0][1], reason="Keep first"
    )

    plan = generate_exact_duplicate_plan(database)

    assert plan.coverage is DuplicateCoverage.PARTIAL
    assert plan.groups[0].state is DuplicatePlanState.BLOCKED
    assert DuplicateBlockKind.INCOMPLETE_COVERAGE in plan.groups[0].blocks


def test_multiple_locations_per_asset_remain_distinct(database, tmp_path) -> None:
    digest, members = _group(database, tmp_path, names=("one.jpg", "two.jpg", "three.jpg"))
    database.execute(
        "UPDATE file_location SET asset_id = ? WHERE id = ?", (members[0][0], members[1][1])
    )
    decision = save_exact_duplicate_decision(
        database, sha256=digest, keep_location_id=members[2][1], reason="Independent copy"
    )

    assert len(decision.members) == 3
    assert [member.asset_id for member in decision.members].count(members[0][0]) == 2
