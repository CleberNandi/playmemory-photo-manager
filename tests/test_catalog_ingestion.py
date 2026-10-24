from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from playmemories_photo_manager.catalog import (
    AssetKind,
    Catalog,
    HashState,
    LocationAvailability,
    initialize_database,
)
from playmemories_photo_manager.catalog_ingestion import (
    CandidateReference,
    CandidateSelection,
    IngestionAuthorization,
    IngestionAuthorizationError,
    IngestionBatchStatus,
    IngestionItemDisposition,
    IngestionProposal,
    apply_ingestion,
    authorize_ingestion,
    candidate_reference,
    plan_fingerprint,
    prepare_ingestion,
)
from playmemories_photo_manager.change_planning import PlanStatus, plan_changes
from playmemories_photo_manager.evidence import evaluate
from playmemories_photo_manager.scanner import (
    ConfinementKind,
    HostPlatform,
    ScanEnvironment,
)

JPEG_BYTES = b"\xff\xd8\xff\xe0synthetic-jpeg\xff\xd9"


@pytest.fixture
def ingestion_setup(tmp_path: Path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    connection = initialize_database(tmp_path / "catalog.sqlite3")
    catalog = Catalog(connection)
    root = catalog.register_root("Synthetic", str(media_root.resolve()))
    yield media_root, connection, catalog, root
    connection.close()


def _write_jpegs(root: Path, names: tuple[str, ...]) -> None:
    for index, name in enumerate(names):
        (root / name).write_bytes(JPEG_BYTES + bytes([index]))


def _selection(proposal: IngestionProposal, path: str) -> CandidateSelection:
    return CandidateSelection(
        candidate_reference(proposal.plan, path), AssetKind.PHOTO, "image/jpeg"
    )


def _authorize_all(proposal: IngestionProposal):
    selections = tuple(
        _selection(proposal, item.relative_path)
        for item in proposal.plan.changes
        if item.classification == "new_file_candidate"
    )
    return authorize_ingestion(proposal.plan, selections)


def _tree_state(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in sorted(root.iterdir())
    }


def test_three_jpeg_vertical_flow_is_persisted_and_queryable(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg", "two.jpg", "three.jpg"))
    before = _tree_state(media_root)

    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    candidates = [
        item for item in proposal.plan.changes if item.classification == "new_file_candidate"
    ]
    authorization = _authorize_all(proposal)
    report = apply_ingestion(catalog, proposal, authorization)

    assert len(candidates) == 3
    assert report.status is IngestionBatchStatus.APPLIED
    assert {item.disposition for item in report.items} == {IngestionItemDisposition.CREATED}
    assert len(catalog.list_assets()) == 3
    locations = catalog.list_root_locations(root.id)
    assert {item.normalized_relative_path for item in locations} == {
        "one.jpg",
        "two.jpg",
        "three.jpg",
    }
    assert all(item.last_seen_at is None for item in locations)
    assert all(asset.hash_state is HashState.ABSENT for asset in catalog.list_assets())
    assert _tree_state(media_root) == before
    assert not any(path.suffix.lower() in {".xmp", ".aae"} for path in media_root.iterdir())


def test_fresh_second_run_and_same_plan_reapplication_are_idempotent(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg", "two.jpg", "three.jpg"))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    authorization = _authorize_all(proposal)

    first = apply_ingestion(catalog, proposal, authorization)
    same_plan = apply_ingestion(catalog, proposal, authorization)
    second_proposal = prepare_ingestion(catalog, root.id, str(media_root))
    empty = authorize_ingestion(second_proposal.plan, ())
    second_run = apply_ingestion(catalog, second_proposal, empty)

    assert all(item.disposition is IngestionItemDisposition.CREATED for item in first.items)
    assert all(
        item.disposition is IngestionItemDisposition.ALREADY_EXISTS for item in same_plan.items
    )
    assert second_run.status is IngestionBatchStatus.EMPTY_SELECTION
    assert all(
        item.classification == "known_location_observed" for item in second_proposal.plan.changes
    )
    assert len(catalog.list_assets()) == len(catalog.list_root_locations(root.id)) == 3


def test_identical_copies_and_hardlink_remain_distinct_assets(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    (media_root / "original.jpg").write_bytes(JPEG_BYTES)
    (media_root / "copy.jpg").write_bytes(JPEG_BYTES)
    try:
        os.link(media_root / "original.jpg", media_root / "hardlink.jpg")
    except OSError as error:  # pragma: no cover - capability dependent
        pytest.skip(f"hardlinks unavailable: {error}")

    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    report = apply_ingestion(catalog, proposal, _authorize_all(proposal))

    assert report.status is IngestionBatchStatus.APPLIED
    assets = catalog.list_assets()
    assert len(assets) == 3
    assert len({asset.id for asset in assets}) == 3
    assert all(asset.sha256 is None and asset.hash_state is HashState.ABSENT for asset in assets)
    locations = catalog.list_root_locations(root.id)
    hardlink_ids = {item.filesystem_id for item in locations if item.filesystem_id is not None}
    assert len(hardlink_ids) == 2


def test_absent_empty_and_partial_authorization_are_distinct(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg", "two.jpg", "three.jpg"))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))

    absent = apply_ingestion(catalog, proposal, None)
    empty = apply_ingestion(catalog, proposal, authorize_ingestion(proposal.plan, ()))
    partial_authorization = authorize_ingestion(proposal.plan, (_selection(proposal, "two.jpg"),))
    partial = apply_ingestion(catalog, proposal, partial_authorization)

    assert absent.status is IngestionBatchStatus.NO_AUTHORIZATION
    assert empty.status is IngestionBatchStatus.EMPTY_SELECTION
    assert partial.status is IngestionBatchStatus.APPLIED
    assert [item.disposition for item in partial.items].count(IngestionItemDisposition.CREATED) == 1
    assert [item.disposition for item in partial.items].count(
        IngestionItemDisposition.IGNORED_NOT_AUTHORIZED
    ) == 2
    assert len(catalog.list_assets()) == 1


def test_authorization_rejects_unknown_duplicate_and_wrong_plan_candidates(
    ingestion_setup,
) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    valid = _selection(proposal, "one.jpg")
    unknown = CandidateSelection(candidate_reference(proposal.plan, "absent.jpg"), AssetKind.PHOTO)
    wrong_plan = CandidateSelection(
        CandidateReference("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", root.id, "one.jpg"),
        AssetKind.PHOTO,
    )

    with pytest.raises(IngestionAuthorizationError, match="not present"):
        authorize_ingestion(proposal.plan, (unknown,))
    with pytest.raises(IngestionAuthorizationError, match="unique"):
        authorize_ingestion(proposal.plan, (valid, valid))
    with pytest.raises(IngestionAuthorizationError, match="this plan"):
        authorize_ingestion(proposal.plan, (wrong_plan,))


def test_blocked_plan_and_incompatible_authorization_are_rejected(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    blocked = replace(proposal.plan, status=PlanStatus.BLOCKED)
    blocked_proposal = replace(proposal, plan=blocked)

    with pytest.raises(IngestionAuthorizationError, match="not eligible"):
        authorize_ingestion(blocked, ())
    blocked_report = apply_ingestion(catalog, blocked_proposal, None)
    assert blocked_report.status is IngestionBatchStatus.REJECTED
    assert blocked_report.items[0].disposition is IngestionItemDisposition.BLOCKED

    valid = _authorize_all(proposal)
    incompatible = replace(valid, plan_fingerprint="0" * 64)
    incompatible_report = apply_ingestion(catalog, proposal, incompatible)
    assert incompatible_report.status is IngestionBatchStatus.REJECTED
    assert catalog.list_assets() == []


def test_plan_inconsistent_with_its_snapshot_is_rejected(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    forged_plan = replace(proposal.plan, changes=())
    forged_proposal = replace(proposal, plan=forged_plan)
    authorization = IngestionAuthorization(
        plan_fingerprint(forged_plan),
        forged_plan.run_id,
        forged_plan.library_root_id,
        (),
        "0" * 64,
    )

    report = apply_ingestion(catalog, forged_proposal, authorization)

    assert report.status is IngestionBatchStatus.REJECTED
    assert report.diagnostic == "plan does not match its assessment and catalog snapshot"
    assert catalog.list_assets() == []


def test_conflict_after_planning_rolls_back_entire_batch(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg", "two.jpg"))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    existing_asset = catalog.create_asset(AssetKind.PHOTO, byte_size=999)
    catalog.register_location(
        existing_asset.id,
        root.id,
        "one.jpg",
        last_seen_at="2026-10-24T00:00:00Z",
        filesystem_id="different",
        observed_byte_size=999,
        observed_mtime_ns=1,
    )

    report = apply_ingestion(catalog, proposal, _authorize_all(proposal))

    assert report.status is IngestionBatchStatus.CONFLICT
    assert all(item.disposition is IngestionItemDisposition.CONFLICT for item in report.items)
    assert len(catalog.list_assets()) == 1
    assert len(catalog.list_root_locations(root.id)) == 1


def test_failure_between_asset_and_location_creation_rolls_back(
    ingestion_setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    media_root, connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))

    def fail_location(_location) -> None:
        raise sqlite3.OperationalError("synthetic location failure")

    monkeypatch.setattr(catalog._repository, "insert_location", fail_location)
    report = apply_ingestion(catalog, proposal, _authorize_all(proposal))

    assert report.status is IngestionBatchStatus.TRANSACTION_FAILED
    assert connection.execute("SELECT count(*) FROM asset").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM file_location").fetchone()[0] == 0


def test_invalid_root_reference_is_a_transaction_failure(ingestion_setup) -> None:
    media_root, connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    authorization = _authorize_all(proposal)
    connection.execute("DELETE FROM library_root WHERE id = ?", (root.id,))

    report = apply_ingestion(catalog, proposal, authorization)

    assert report.status is IngestionBatchStatus.TRANSACTION_FAILED
    assert catalog.list_assets() == []


def test_two_connections_cannot_duplicate_an_active_path(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    _write_jpegs(media_root, ("one.jpg",))
    database_path = tmp_path / "catalog.sqlite3"
    first_connection = initialize_database(database_path)
    second_connection = initialize_database(database_path)
    try:
        first_catalog = Catalog(first_connection)
        second_catalog = Catalog(second_connection)
        root = first_catalog.register_root("Synthetic", str(media_root.resolve()))
        proposal = prepare_ingestion(first_catalog, root.id, str(media_root))
        authorization = _authorize_all(proposal)

        first = apply_ingestion(first_catalog, proposal, authorization)
        second = apply_ingestion(second_catalog, proposal, authorization)

        assert first.items[0].disposition is IngestionItemDisposition.CREATED
        assert second.items[0].disposition is IngestionItemDisposition.ALREADY_EXISTS
        assert len(second_catalog.list_assets()) == 1
        assert len(second_catalog.list_root_locations(root.id)) == 1
    finally:
        first_connection.close()
        second_connection.close()


def test_authorization_is_bound_to_plan_fingerprint(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    authorization = _authorize_all(proposal)

    assert authorization.plan_fingerprint == plan_fingerprint(proposal.plan)
    forged = IngestionAuthorization(
        authorization.plan_fingerprint,
        authorization.run_id,
        authorization.library_root_id,
        (
            CandidateSelection(
                CandidateReference(
                    authorization.run_id,
                    authorization.library_root_id,
                    "outside.jpg",
                ),
                AssetKind.PHOTO,
            ),
        ),
        "0" * 64,
    )
    report = apply_ingestion(catalog, proposal, forged)
    assert report.status is IngestionBatchStatus.REJECTED
    assert catalog.list_assets() == []


def test_existing_location_is_never_reported_as_new_creation(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    first_proposal = prepare_ingestion(catalog, root.id, str(media_root))
    apply_ingestion(catalog, first_proposal, _authorize_all(first_proposal))

    second_proposal = prepare_ingestion(catalog, root.id, str(media_root))
    report = apply_ingestion(
        catalog, second_proposal, authorize_ingestion(second_proposal.plan, ())
    )

    assert report.items[0].disposition is IngestionItemDisposition.ALREADY_EXISTS
    assert second_proposal.plan.changes[0].classification == "known_location_observed"
    location = catalog.list_root_locations(root.id)[0]
    assert location.availability is LocationAvailability.PRESENT


def test_authorization_cannot_be_expanded_after_the_decision(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg", "two.jpg"))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))
    authorization = authorize_ingestion(proposal.plan, (_selection(proposal, "one.jpg"),))
    expanded = replace(
        authorization,
        selections=authorization.selections + (_selection(proposal, "two.jpg"),),
    )

    report = apply_ingestion(catalog, proposal, expanded)

    assert report.status is IngestionBatchStatus.REJECTED
    assert report.diagnostic == "authorization selections changed after the explicit decision"
    assert catalog.list_assets() == []


def test_path_based_or_unrecorded_confinement_cannot_be_applied(ingestion_setup) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    original = prepare_ingestion(catalog, root.id, str(media_root))

    for environment in (
        ScanEnvironment(HostPlatform.WINDOWS, ConfinementKind.PATH_BASED),
        None,
    ):
        scan_result = replace(original.scan_result, environment=environment)
        assessment = evaluate(scan_result)
        plan = plan_changes(assessment, original.catalog_snapshot, original.planning_context)
        proposal = replace(original, scan_result=scan_result, assessment=assessment, plan=plan)
        authorization = authorize_ingestion(plan, (_selection(proposal, "one.jpg"),))

        report = apply_ingestion(catalog, proposal, authorization)

        assert report.status is IngestionBatchStatus.REJECTED
        assert "confinement_not_demonstrated" in report.diagnostic
    assert catalog.list_assets() == []


def test_commit_failure_rolls_back_the_batch(ingestion_setup) -> None:
    media_root, connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))

    def deny_commit(action, argument, _arg2, _database, _trigger):
        if action == sqlite3.SQLITE_TRANSACTION and argument == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(deny_commit)
    try:
        report = apply_ingestion(catalog, proposal, _authorize_all(proposal))
    finally:
        connection.set_authorizer(None)

    assert report.status is IngestionBatchStatus.TRANSACTION_FAILED
    assert connection.in_transaction is False
    assert connection.execute("SELECT count(*) FROM asset").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM file_location").fetchone()[0] == 0


def test_rollback_failure_is_explicit_and_connection_is_not_reused_silently(
    ingestion_setup,
) -> None:
    media_root, connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    proposal = prepare_ingestion(catalog, root.id, str(media_root))

    def deny_end_transaction(action, argument, _arg2, _database, _trigger):
        if action == sqlite3.SQLITE_TRANSACTION and argument in {"COMMIT", "ROLLBACK"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(deny_end_transaction)
    report = apply_ingestion(catalog, proposal, _authorize_all(proposal))
    connection.set_authorizer(None)
    try:
        assert report.status is IngestionBatchStatus.TRANSACTION_FAILED
        assert "rollback also failed" in report.diagnostic
        assert connection.in_transaction is True
    finally:
        connection.rollback()
    assert connection.execute("SELECT count(*) FROM asset").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM file_location").fetchone()[0] == 0


def test_historical_missing_path_can_be_registered_as_a_new_asset(ingestion_setup) -> None:
    media_root, connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("reused.jpg",))
    historical_asset = catalog.create_asset(AssetKind.PHOTO)
    connection.execute(
        """INSERT INTO file_location(
            id, asset_id, library_root_id, normalized_relative_path, entry_type, availability
        ) VALUES (?, ?, ?, 'reused.jpg', 'file', 'missing')""",
        (str(uuid.uuid4()), historical_asset.id, root.id),
    )
    proposal = prepare_ingestion(catalog, root.id, str(media_root))

    report = apply_ingestion(catalog, proposal, _authorize_all(proposal))

    assert report.items[0].disposition is IngestionItemDisposition.CREATED
    assert len(catalog.list_assets()) == 2
    locations = catalog.list_root_locations(root.id)
    assert {item.availability for item in locations} == {
        LocationAvailability.MISSING,
        LocationAvailability.PRESENT,
    }


def test_physical_replacement_at_an_active_path_does_not_create_or_merge_asset(
    ingestion_setup,
) -> None:
    media_root, _connection, catalog, root = ingestion_setup
    _write_jpegs(media_root, ("one.jpg",))
    first_proposal = prepare_ingestion(catalog, root.id, str(media_root))
    apply_ingestion(catalog, first_proposal, _authorize_all(first_proposal))
    original_asset = catalog.list_assets()[0]
    replacement = media_root / "replacement.tmp"
    replacement.write_bytes(b"x" * len((media_root / "one.jpg").read_bytes()))
    replacement.replace(media_root / "one.jpg")

    second_proposal = prepare_ingestion(catalog, root.id, str(media_root))
    report = apply_ingestion(
        catalog, second_proposal, authorize_ingestion(second_proposal.plan, ())
    )

    assert report.status is IngestionBatchStatus.REJECTED
    assert report.items[0].disposition is IngestionItemDisposition.BLOCKED
    assert "changed at active path" in report.diagnostic
    assert catalog.list_assets() == [original_asset]
    assert len(catalog.list_root_locations(root.id)) == 1
