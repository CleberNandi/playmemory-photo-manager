import os
import sqlite3
from dataclasses import replace

import pytest
from jpeg_fixtures import jpeg

from playmemories_photo_manager.catalog import Catalog, connect, initialize_database
from playmemories_photo_manager.catalog_ingestion import (
    IngestionBatchStatus,
    IngestionItemDisposition,
    SnapshotLimits,
    apply_scoped_ingestion,
    authorize_scoped_ingestion,
    capture_catalog_snapshot,
    classify_media,
    prepare_from_snapshot,
    scope_catalogable_proposal,
    scoped_application,
    scoped_preflight,
)
from playmemories_photo_manager.catalog_ingestion.media import _mount_id
from playmemories_photo_manager.change_planning import PlanningContext
from playmemories_photo_manager.scanner import ScanLimits, ScanOptions, scan


def prepare(root, path, root_id):
    observed = scan(root, ScanOptions(limits=ScanLimits()))
    original = prepare_from_snapshot(
        capture_catalog_snapshot(path, root_id, limits=SnapshotLimits()),
        observed,
        PlanningContext(root_id, str(root), str(root), observed.scope),
    )
    return scope_catalogable_proposal(original, classify_media(observed, root_id))


def authorize(scoped):
    return authorize_scoped_ingestion(
        scoped,
        tuple(
            item.candidate_id
            for item in scoped.eligibilities
            if item.candidate in scoped.eligible_candidates
        ),
    )


@pytest.fixture
def batch(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    (root / "nested").mkdir()
    (root / "nested" / "a.jpg").write_bytes(jpeg(3))
    (root / "b.jpg").write_bytes(jpeg(3))
    (root / "notes.txt").write_text("synthetic exclusion")
    path = tmp_path / "catalog.sqlite3"
    connection = initialize_database(path)
    catalog = Catalog(connection)
    registered = catalog.register_root("Synthetic", str(root))
    scoped = prepare(root, path, registered.id)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        mount = _mount_id(fd)
    finally:
        os.close(fd)
    try:
        yield root, path, connection, catalog, scoped, authorize(scoped), mount
    finally:
        connection.close()


def counts(path):
    with connect(path) as connection:
        return tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("asset", "file_location")
        )


def test_creates_independent_assets_atomically_without_modifying_originals(batch):
    root, path, connection, catalog, scoped, auth, mount = batch
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert report.status is IngestionBatchStatus.APPLIED
    assert len({item.asset_id for item in report.items}) == 2
    assert all(item.disposition is IngestionItemDisposition.CREATED for item in report.items)
    assert counts(path) == (2, 2)
    assert not connection.in_transaction
    assert all(
        asset.sha256 is None and asset.media_type == "image/jpeg" for asset in catalog.list_assets()
    )
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before
    assert not (root / "catalog.sqlite3").exists()


def test_selected_subset_only_and_reprepare_is_empty_without_duplicating_paths(batch):
    root, path, _, catalog, scoped, auth, mount = batch
    one = authorize_scoped_ingestion(scoped, auth.candidate_ids[:1])
    report = apply_scoped_ingestion(catalog, scoped, one, expected_root_mount=mount)
    assert [item.disposition for item in report.items].count(IngestionItemDisposition.CREATED) == 1
    assert counts(path) == (1, 1)
    updated = prepare(root, path, scoped.original.plan.library_root_id)
    assert len(updated.eligible_candidates) == 1
    assert (
        apply_scoped_ingestion(
            catalog, updated, authorize(updated), expected_root_mount=mount
        ).status
        is IngestionBatchStatus.APPLIED
    )
    again = prepare(root, path, scoped.original.plan.library_root_id)
    assert not again.eligible_candidates
    assert (
        apply_scoped_ingestion(catalog, again, authorize(again), expected_root_mount=mount).status
        is IngestionBatchStatus.EMPTY_SELECTION
    )
    assert counts(path) == (2, 2)


@pytest.mark.parametrize("choice", ["absent", "empty", "forged"])
def test_noop_or_invalid_consent_never_reads_media_or_begins_a_write(batch, monkeypatch, choice):
    _, path, connection, catalog, scoped, auth, mount = batch
    events = []
    connection.set_trace_callback(events.append)
    monkeypatch.setattr(
        scoped_application,
        "preflight_scoped_ingestion",
        lambda *_a, **_k: pytest.fail("preflight admitted"),
    )
    selected = (
        None
        if choice == "absent"
        else authorize_scoped_ingestion(scoped, ())
        if choice == "empty"
        else replace(auth, decision_fingerprint="forged")
    )
    report = apply_scoped_ingestion(catalog, scoped, selected, expected_root_mount=mount)
    expected = {
        "absent": IngestionBatchStatus.NO_AUTHORIZATION,
        "empty": IngestionBatchStatus.EMPTY_SELECTION,
        "forged": IngestionBatchStatus.REJECTED,
    }
    assert report.status is expected[choice]
    assert not events
    assert counts(path) == (0, 0)


def test_physical_preflight_is_outside_the_single_write_transaction(batch, monkeypatch):
    _, path, connection, catalog, scoped, auth, mount = batch
    verify = scoped_preflight._verify_file
    snapshot = scoped_application._capture_connection_snapshot
    media_calls = []
    snapshots = []

    def checked_file(*args):
        assert not connection.in_transaction
        media_calls.append(1)
        return verify(*args)

    def checked_snapshot(*args):
        assert connection.in_transaction
        with (
            connect(path, timeout=0) as other,
            pytest.raises(sqlite3.OperationalError, match="locked"),
        ):
            other.execute("BEGIN IMMEDIATE")
        snapshots.append(1)
        return snapshot(*args)

    monkeypatch.setattr(scoped_preflight, "_verify_file", checked_file)
    monkeypatch.setattr(scoped_application, "_capture_connection_snapshot", checked_snapshot)
    events = []
    connection.set_trace_callback(events.append)
    assert (
        apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount).status
        is IngestionBatchStatus.APPLIED
    )
    assert len(media_calls) == 2 and len(snapshots) == 1
    assert sum(sql == "BEGIN IMMEDIATE" for sql in events) == 1
    assert sum(sql == "COMMIT" for sql in events) == 1


def test_physical_change_blocks_all_creations(batch):
    root, path, _, catalog, scoped, auth, mount = batch
    (root / "b.jpg").unlink()
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert report.status is IngestionBatchStatus.REJECTED
    assert report.diagnostic == "source_changed"
    assert counts(path) == (0, 0)


def test_stale_catalog_blocks_the_whole_batch_even_if_paths_were_already_created(batch):
    _, path, _, catalog, scoped, auth, mount = batch
    assert (
        apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount).status
        is IngestionBatchStatus.APPLIED
    )
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert report.status is IngestionBatchStatus.CONFLICT
    assert all(item.asset_id is None for item in report.items)
    assert counts(path) == (2, 2)


@pytest.mark.parametrize("fail_at", [1, 2])
def test_location_failure_after_asset_insert_rolls_back_everything(batch, monkeypatch, fail_at):
    _, path, connection, catalog, scoped, auth, mount = batch
    inserted = []
    insert = catalog._repository.insert_asset

    def record(*args):
        inserted.append(1)
        return insert(*args)

    monkeypatch.setattr(catalog._repository, "insert_asset", record)

    location_insert = catalog._repository.insert_location

    def fail(location):
        if len(inserted) == fail_at:
            raise sqlite3.OperationalError("synthetic storage failure")
        return location_insert(location)

    monkeypatch.setattr(catalog._repository, "insert_location", fail)
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert inserted
    assert report.status is IngestionBatchStatus.TRANSACTION_FAILED
    assert not connection.in_transaction and counts(path) == (0, 0)
    assert all(item.asset_id is None and item.location_id is None for item in report.items)


@pytest.mark.parametrize("deny_rollback", [False, True])
def test_commit_failure_is_unknown_and_connection_is_discarded(batch, deny_rollback):
    _, path, connection, catalog, scoped, auth, mount = batch

    def deny(action, argument, *_args):
        if action == sqlite3.SQLITE_TRANSACTION and (
            argument == "COMMIT" or deny_rollback and argument == "ROLLBACK"
        ):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(deny)
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert (
        report.status is IngestionBatchStatus.TRANSACTION_FAILED
        and report.diagnostic == "outcome_unknown"
    )
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    assert counts(path) == (0, 0)


@pytest.mark.parametrize("failure", [sqlite3.OperationalError, RuntimeError])
def test_error_after_commit_never_returns_a_false_rollback_result(batch, failure):
    _, path, connection, catalog, scoped, auth, mount = batch

    class LostAcknowledgement:
        def __getattr__(self, key):
            return getattr(connection, key)

        def commit(self):
            connection.commit()
            raise failure("synthetic lost acknowledgement")

    catalog._connection = LostAcknowledgement()
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert report.diagnostic == "outcome_unknown"
    assert report.status is IngestionBatchStatus.TRANSACTION_FAILED
    assert counts(path) == (2, 2)  # Durable data can exist even though the caller saw an error.
    assert all(item.asset_id is None for item in report.items)


def test_does_not_rollback_a_callers_existing_transaction(batch):
    _, path, connection, catalog, scoped, auth, mount = batch
    connection.execute("BEGIN IMMEDIATE")
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert report.diagnostic == "active_transaction" and connection.in_transaction
    connection.rollback()
    assert counts(path) == (0, 0)


def test_database_race_after_media_verification_blocks_all_creations(batch, monkeypatch):
    _, path, _, catalog, scoped, auth, mount = batch
    register = catalog._register_new_files_atomically

    def race(*args, **kwargs):
        with connect(path) as other:
            other.execute(
                "UPDATE library_root SET display_name = ? WHERE id = ?",
                ("Changed after review", scoped.original.plan.library_root_id),
            )
        return register(*args, **kwargs)

    monkeypatch.setattr(catalog, "_register_new_files_atomically", race)
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert report.status is IngestionBatchStatus.CONFLICT
    assert counts(path) == (0, 0)


def test_root_race_at_transaction_boundary_blocks_all_creations(batch, monkeypatch):
    root, path, _, catalog, scoped, auth, mount = batch
    register = catalog._register_new_files_atomically

    def race(*args, **kwargs):
        root.rename(root.with_name("old-media"))
        root.mkdir()
        return register(*args, **kwargs)

    monkeypatch.setattr(catalog, "_register_new_files_atomically", race)
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert report.status is IngestionBatchStatus.REJECTED and report.diagnostic == "source_changed"
    assert counts(path) == (0, 0)


def test_snapshot_budgets_apply_inside_transaction_and_restore_connection_limit(batch, monkeypatch):
    _, path, connection, catalog, scoped, auth, mount = batch
    connection.execute(
        "UPDATE library_root SET display_name = ? WHERE id = ?",
        ("x" * 2000, scoped.original.plan.library_root_id),
    )
    connection.commit()
    original_limit = connection.getlimit(sqlite3.SQLITE_LIMIT_LENGTH)
    monkeypatch.setattr(scoped_application, "SnapshotLimits", lambda: SnapshotLimits(max_bytes=512))
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert report.status is IngestionBatchStatus.REJECTED and report.diagnostic == "resource_limit"
    assert connection.getlimit(sqlite3.SQLITE_LIMIT_LENGTH) == original_limit
    assert not connection.in_transaction and counts(path) == (0, 0)


def test_insert_and_rollback_failure_suspends_connection(batch, monkeypatch):
    _, path, connection, catalog, scoped, auth, mount = batch

    def deny(action, argument, *_args):
        return (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_TRANSACTION and argument == "ROLLBACK"
            else sqlite3.SQLITE_OK
        )

    def fail(_location):
        raise sqlite3.OperationalError("synthetic failed location")

    monkeypatch.setattr(catalog._repository, "insert_location", fail)
    connection.set_authorizer(deny)
    report = apply_scoped_ingestion(catalog, scoped, auth, expected_root_mount=mount)
    assert (
        report.status is IngestionBatchStatus.TRANSACTION_FAILED
        and report.diagnostic == "outcome_unknown"
    )
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    assert counts(path) == (0, 0)


def test_negative_filesystem_mtime_is_rejected_before_writes(batch):
    root, path, connection, catalog, scoped, _, mount = batch
    os.utime(root / "b.jpg", ns=(0, -1000000000))
    updated = prepare(root, path, scoped.original.plan.library_root_id)
    events = []
    connection.set_trace_callback(events.append)
    report = apply_scoped_ingestion(catalog, updated, authorize(updated), expected_root_mount=mount)
    assert (
        report.status is IngestionBatchStatus.REJECTED
        and report.diagnostic == "invalid_observation"
    )
    assert not events and counts(path) == (0, 0)
