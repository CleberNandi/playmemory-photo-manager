"""Only temporary catalogs and synthetic media trees are used here."""

import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from playmemories_photo_manager.catalog import Catalog, initialize_database
from playmemories_photo_manager.catalog.repository import CatalogRepository
from playmemories_photo_manager.catalog_ingestion import (
    SnapshotLimits,
    SnapshotResourceLimitError,
    capture_catalog_snapshot,
    prepare_from_snapshot,
    prepare_ingestion,
)
from playmemories_photo_manager.catalog_ingestion import snapshot as snapshot_module
from playmemories_photo_manager.change_planning import PlanningContext, PlanStatus
from playmemories_photo_manager.library import LibraryError, lifecycle, read_library_connection
from playmemories_photo_manager.scanner import ScanLimits, ScanOptions, scan


@pytest.fixture
def catalog_fixture(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    media = tmp_path / "media"
    media.mkdir()
    connection = initialize_database(path)
    catalog = Catalog(connection)
    root = catalog.register_root("Synthetic", str(media))
    yield path, media, connection, catalog, root
    connection.close()


def _locations(connection, root, count):
    asset_id = str(uuid4())
    connection.execute("BEGIN")
    try:
        connection.execute("INSERT INTO asset(id,kind) VALUES (?, 'photo')", (asset_id,))
        connection.executemany(
            "INSERT INTO file_location(id,asset_id,library_root_id,normalized_relative_path,"
            "entry_type,availability) VALUES (?,?,?,?, 'file','present')",
            [(str(uuid4()), asset_id, root.id, f"{i:04}.jpg") for i in range(count)],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def test_snapshot_and_pure_builder_match_legacy_and_close_before_scan(catalog_fixture, monkeypatch):
    path, media, _connection, catalog, root = catalog_fixture
    (media / "synthetic.jpg").write_bytes(b"not validated in this layer")
    legacy = prepare_ingestion(catalog, root.id, str(media), ScanOptions(limits=ScanLimits()))
    before = {p.name for p in path.parent.iterdir()}
    modes = []
    connections = []
    original = lifecycle._Selection.connection

    def track(selection, mode):
        modes.append(mode)
        result = original(selection, mode)
        connections.append(result)
        return result

    monkeypatch.setattr(lifecycle._Selection, "connection", track)
    snapshot = capture_catalog_snapshot(path, root.id)
    assert modes == ["ro"]
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    assert snapshot == legacy.catalog_snapshot
    context = legacy.planning_context
    proposal = prepare_from_snapshot(snapshot, legacy.scan_result, context)
    assert proposal == legacy
    assert catalog.list_assets() == []
    assert {p.name for p in path.parent.iterdir()} == before
    # Snapshot is now disconnected: new scan/planning needs no database capability.
    monkeypatch.setattr(
        snapshot_module, "read_library_connection", lambda *_a, **_k: pytest.fail("no reconnect")
    )
    observed = scan(media, ScanOptions(limits=ScanLimits()))
    assert prepare_from_snapshot(snapshot, observed, context).scan_result == observed


def test_snapshot_consistent_transaction_blocks_external_commit(catalog_fixture, monkeypatch):
    path, _media, connection, _catalog, root = catalog_fixture
    _locations(connection, root, 101)
    original = CatalogRepository.iter_assets
    seen = []

    def get_assets(catalog, ids):
        seen.append(len(ids))
        external = sqlite3.connect(path, timeout=0)
        try:
            external.execute(
                "UPDATE library_root SET display_name='Changed' WHERE id=?", (root.id,)
            )
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                external.commit()
        finally:
            external.rollback()
            external.close()
        return original(catalog, ids)

    monkeypatch.setattr(CatalogRepository, "iter_assets", get_assets)
    captured = capture_catalog_snapshot(path, root.id)
    assert captured.library_root.display_name == "Synthetic"
    assert len(captured.locations) == 101
    assert seen == [1]  # shared asset loaded only once
    # No reader lock survives return.
    connection.execute("UPDATE library_root SET display_name='After close' WHERE id=?", (root.id,))


def test_distinct_assets_are_loaded_in_batches_of_100(catalog_fixture, monkeypatch):
    path, _media, connection, _catalog, root = catalog_fixture
    identifiers = [str(uuid4()) for _ in range(101)]
    connection.execute("BEGIN")
    connection.executemany(
        "INSERT INTO asset(id,kind) VALUES (?, 'photo')",
        [(identifier,) for identifier in identifiers],
    )
    connection.executemany(
        "INSERT INTO file_location(id,asset_id,library_root_id,normalized_relative_path,"
        "entry_type,availability) VALUES (?,?,?,?, 'file','present')",
        [
            (str(uuid4()), identifier, root.id, f"{i}.jpg")
            for i, identifier in enumerate(identifiers)
        ],
    )
    connection.commit()
    original = CatalogRepository.iter_assets
    sizes = []

    def get_assets(catalog, ids):
        sizes.append(len(ids))
        return original(catalog, ids)

    monkeypatch.setattr(CatalogRepository, "iter_assets", get_assets)
    captured = capture_catalog_snapshot(path, root.id)
    assert len(captured.assets) == 101
    assert sizes == [100, 1]


def test_snapshot_budget_covers_accumulation_not_only_individual_cells(
    catalog_fixture, monkeypatch
):
    path, _media, connection, _catalog, root = catalog_fixture
    _locations(connection, root, 300)
    original = CatalogRepository.iter_root_locations
    consumed = 0

    def rows(repository, *args):
        nonlocal consumed
        for item in original(repository, *args):
            consumed += 1
            yield item

    monkeypatch.setattr(CatalogRepository, "iter_root_locations", rows)
    with pytest.raises(SnapshotResourceLimitError, match="resource_limit"):
        capture_catalog_snapshot(path, root.id, limits=SnapshotLimits(max_bytes=65536))
    assert 0 < consumed < 300


def test_location_limit_exactly_2000_and_single_excess_row(catalog_fixture, monkeypatch):
    path, _media, connection, _catalog, root = catalog_fixture
    _locations(connection, root, 2000)
    assert len(capture_catalog_snapshot(path, root.id).locations) == 2000
    asset = Catalog(connection).list_assets()[0]
    connection.execute(
        "INSERT INTO file_location(id,asset_id,library_root_id,normalized_relative_path,"
        "entry_type,availability) VALUES (?,?,?,?, 'file','present')",
        (str(uuid4()), asset.id, root.id, "extra.jpg"),
    )
    original = CatalogRepository.iter_root_locations
    loaded = 0

    def page(catalog, *args, **kwargs):
        nonlocal loaded
        for item in original(catalog, *args, **kwargs):
            loaded += 1
            yield item

    monkeypatch.setattr(CatalogRepository, "iter_root_locations", page)
    with pytest.raises(SnapshotResourceLimitError) as caught:
        capture_catalog_snapshot(path, root.id)
    assert caught.value.reason == "max_locations"
    assert loaded == 2001
    assert str(path) not in str(caught.value)


def test_canonical_byte_budget_counts_utf8_escaping_and_all_records(catalog_fixture):
    path, _media, connection, _catalog, root = catalog_fixture
    # One row fits SQLite's value budget; its JSON ASCII representation does not.
    connection.execute("UPDATE library_root SET display_name=? WHERE id=?", ("é" * 12000, root.id))
    with pytest.raises(SnapshotResourceLimitError) as caught:
        capture_catalog_snapshot(path, root.id, limits=SnapshotLimits(max_bytes=65536))
    assert caught.value.reason == "max_bytes"


def test_sqlite_value_limit_prevents_huge_cell_materialization(catalog_fixture):
    path, _media, connection, _catalog, root = catalog_fixture
    connection.execute("UPDATE library_root SET display_name=? WHERE id=?", ("x" * 70000, root.id))
    with pytest.raises(SnapshotResourceLimitError) as caught:
        capture_catalog_snapshot(path, root.id, limits=SnapshotLimits(max_bytes=65536))
    assert caught.value.reason == "max_bytes"
    assert connection.in_transaction is False
    connection.execute("UPDATE library_root SET display_name='Restored' WHERE id=?", (root.id,))
    assert capture_catalog_snapshot(path, root.id).library_root.display_name == "Restored"


def test_reader_rolls_back_and_closes_on_caller_exception(catalog_fixture):
    path, *_ = catalog_fixture
    with (
        pytest.raises(RuntimeError, match="synthetic error"),
        read_library_connection(path) as connection,
    ):
        connection.execute("BEGIN")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM library_root")
        raise RuntimeError("synthetic error")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_pure_builder_preserves_scope_mismatch_as_blocked(catalog_fixture):
    path, media, _connection, _catalog, root = catalog_fixture
    snapshot = capture_catalog_snapshot(path, root.id)
    observed = scan(media)
    context = PlanningContext(root.id, str(media), str(media), observed.scope)
    wrong = replace(snapshot, effective_scope=replace(snapshot.effective_scope, recursive=False))
    assert prepare_from_snapshot(wrong, observed, context).plan.status is PlanStatus.BLOCKED


@pytest.mark.parametrize("value", [0, -1, True, 2001, "100"])
def test_snapshot_limit_validation(value):
    with pytest.raises(ValueError):
        SnapshotLimits(max_locations=value)


def test_reader_rejects_clean_wal_before_connect_without_auxiliaries(tmp_path, monkeypatch):
    path = tmp_path / "wal.sqlite3"
    connection = initialize_database(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.close()
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    monkeypatch.setattr(lifecycle, "connect", lambda *_a, **_k: pytest.fail("WAL opened"))
    with (
        pytest.raises(LibraryError, match="incompatible"),
        read_library_connection(path),
    ):
        pytest.fail("WAL was admitted")
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_reader_path_swapped_before_return_rejects_snapshot(catalog_fixture, monkeypatch):
    path, _media, _connection, _catalog, root = catalog_fixture
    original = Catalog.get_root

    def swapped(catalog, identifier):
        result = original(catalog, identifier)
        path.rename(path.with_suffix(".retained"))
        path.write_bytes(b"replacement")
        return result

    monkeypatch.setattr(Catalog, "get_root", swapped)
    with pytest.raises(LibraryError, match="unsafe_location"):
        capture_catalog_snapshot(path, root.id)


def test_reader_rejects_symlink_and_preserves_original(catalog_fixture, tmp_path):
    path, *_ = catalog_fixture
    before = path.read_bytes()
    alias = tmp_path / "alias.sqlite3"
    alias.symlink_to(path)
    with (
        pytest.raises(LibraryError, match="unsafe_location"),
        read_library_connection(alias),
    ):
        pytest.fail("symlink admitted")
    assert path.read_bytes() == before
