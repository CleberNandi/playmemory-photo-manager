"""Registered-root additions across sessions without native reselection."""

import time
from uuid import uuid4

import pytest
from test_real_images_calendar import apply, raster

from playmemories_photo_manager.catalog import Catalog, connect
from playmemories_photo_manager.desktop.libraries import LibraryDispatcher


@pytest.fixture
def library(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    path = tmp_path / "catalog.sqlite3"
    dispatcher = LibraryDispatcher(ingestion_enabled=True, index_state=profile / "roots.json")
    session = dispatcher.request(
        "library.create", {"path": str(path), "library_handle": str(uuid4())}
    )["session"]["session_id"]
    root = tmp_path / "media"
    root.mkdir()
    raster(root / "first.jpg")
    with connect(path) as connection:
        root_id = Catalog(connection).register_root("Synthetic", str(root)).id
        apply(root, path, connection, root_id)
    yield dispatcher, path, session, root, profile
    dispatcher.close()


def settle(dispatcher, session, force=True):
    if force:
        dispatcher.request("index.refresh", {"session_id": session})
    for _ in range(800):
        status = dispatcher.request("index.pulse", {"session_id": session, "allow": True})
        dispatcher.tick()
        if status["last_check"] is not None and not status["busy"] and not dispatcher.indexer.queue:
            return status
        if status["error"] and not status["busy"] and not dispatcher.indexer.queue:
            return status
        time.sleep(0.01)
    raise AssertionError("indexer did not settle")


def test_legacy_root_is_backfilled_and_new_file_appears_without_reselection(library):
    dispatcher, _, session, root, profile = library
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    raster(root / "new.jpg")
    status = settle(dispatcher, session)
    assert status["error"] is None, status
    assert status["added_count"] == 1
    assert len(dispatcher.request("gallery.list", {"session_id": session})["items"]) == 2
    assert (profile / "roots.json").stat().st_mode & 0o077 == 0
    assert not status.get("path")


def test_restart_finds_files_added_while_application_was_closed(library):
    dispatcher, path, session, root, _ = library
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    assert settle(dispatcher, session)["error"] is None
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    dispatcher.request("library.close", {"session_id": session})
    raster(root / "after-restart.jpg")
    session = dispatcher.request(
        "library.open", {"path": str(path), "library_handle": str(uuid4())}
    )["session"]["session_id"]
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    result = settle(dispatcher, session)
    assert result["error"] is None, result
    assert len(dispatcher.request("gallery.list", {"session_id": session})["items"]) == 2


def test_root_replacement_is_not_silently_authorized(library):
    dispatcher, _, session, root, _ = library
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    assert settle(dispatcher, session)["error"] is None
    moved = root.with_name("old")
    root.rename(moved)
    root.mkdir()
    raster(root / "replacement.jpg")
    result = settle(dispatcher, session)
    assert result["error"] == "root_changed", result
    assert len(dispatcher.request("gallery.list", {"session_id": session})["items"]) == 1


def test_no_duplicate_additions_on_repeated_cycles(library):
    dispatcher, _, session, _, _ = library
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    assert settle(dispatcher, session)["error"] is None
    previous = dispatcher.indexer.last_check
    dispatcher.indexer.last_check = None
    result = settle(dispatcher, session)
    assert result["error"] is None, result
    assert result["last_check"] >= previous
    assert result["added_count"] == 0
    assert len(dispatcher.request("gallery.list", {"session_id": session})["items"]) == 1


def test_new_empty_selection_stays_monitored_after_reopen(library):
    dispatcher, path, session, root, _ = library
    empty = root.with_name("empty")
    empty.mkdir()
    dispatcher.request(
        "ingestion.select_root",
        {
            "session_id": session,
            "window_id": str(uuid4()),
            "path": str(empty),
            "recursive": True,
            "identity_reviewed": True,
        },
    )
    dispatcher.request("library.close", {"session_id": session})
    raster(empty / "added-while-closed.jpg")
    session = dispatcher.request(
        "library.open", {"path": str(path), "library_handle": str(uuid4())}
    )["session"]["session_id"]
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    result = settle(dispatcher, session)
    assert result["error"] is None, result
    assert len(dispatcher.request("gallery.list", {"session_id": session})["items"]) == 2


def test_private_state_symlink_fails_closed(library, tmp_path):
    dispatcher, _, session, _, profile = library
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (profile / "roots.json").symlink_to(outside)
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    result = settle(dispatcher, session)
    assert result["error"] is not None
    assert outside.read_text() == "{}"
    assert result["added_count"] == 0


def test_pausing_reaps_background_read_before_a_foreground_write(library):
    dispatcher, _, session, _, _ = library
    dispatcher.request("index.pulse", {"session_id": session, "allow": True})
    dispatcher.tick()
    for _ in range(500):
        result = dispatcher.request("index.pulse", {"session_id": session, "allow": False})
        dispatcher.tick()
        if not result["busy"]:
            break
        time.sleep(0.01)
    assert not result["busy"]
    asset = dispatcher.request("gallery.list", {"session_id": session})["items"][0]["asset_id"]
    assert dispatcher.request(
        "annotation.favorite", {"session_id": session, "asset_id": asset, "favorite": True}
    )["favorite"]


def test_periodic_scan_skips_unchanged_images_and_notices_empty_subfolder_addition(
    library, monkeypatch
):
    from playmemories_photo_manager.catalog_ingestion.root_grants import RootGrantService

    dispatcher, _, session, root, _ = library
    nested = root / "empty-subfolder"
    nested.mkdir()
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    assert settle(dispatcher, session)["error"] is None
    original = RootGrantService.select_monitored
    calls = []

    def watched(self, *args):
        calls.append(args)
        return original(self, *args)

    monkeypatch.setattr(RootGrantService, "select_monitored", watched)
    dispatcher.indexer.due = 0
    dispatcher.indexer.last_check = None
    assert settle(dispatcher, session, force=False)["error"] is None
    assert not calls
    raster(nested / "new.jpg")
    dispatcher.indexer.due = 0
    dispatcher.indexer.last_check = None
    result = settle(dispatcher, session, force=False)
    assert result["error"] is None, result
    assert calls
    assert result["added_count"] == 1


def test_one_unavailable_root_does_not_block_other_registered_folders(library):
    dispatcher, path, session, root, _ = library
    with connect(path) as connection:
        Catalog(connection).register_root("Unavailable", str(root.with_name("missing")))
    raster(root / "new.jpg")
    dispatcher.request("index.pulse", {"session_id": session, "allow": False})
    result = settle(dispatcher, session)
    assert result["error"] is not None
    assert result["added_count"] == 1, result
    assert len(dispatcher.request("gallery.list", {"session_id": session})["items"]) == 2


@pytest.mark.parametrize("change", ["mtime", "delete", "replace"])
def test_anchored_root_discovers_additions_after_known_file_changes(library, change):
    dispatcher, _, session, root, _ = library
    assert settle(dispatcher, session)["error"] is None
    existing = root / "first.jpg"
    if change == "delete":
        existing.unlink()
    elif change == "replace":
        replacement = root / "replacement.jpg"
        raster(replacement)
        replacement.replace(existing)
    else:
        import os

        info = existing.stat()
        os.utime(existing, ns=(info.st_atime_ns, info.st_mtime_ns - 1_000_000_000))
    raster(root / "new.jpg")
    result = settle(dispatcher, session)
    assert result["error"] is None, result
    assert result["added_count"] == 1


def test_filesystem_events_retry_incomplete_jpeg_without_waiting_for_poll(library):
    dispatcher, _, session, root, _ = library
    assert settle(dispatcher, session)["error"] is None
    dispatcher.indexer.interval = 3600
    dispatcher.indexer.due = time.monotonic() + 3600
    assert any(events.fd >= 0 for events in dispatcher.indexer.watches.values())
    target = root / "copy.jpg"
    source = (root / "first.jpg").read_bytes()
    target.write_bytes(source[:128])
    raster(root / "unrelated.jpg")
    dispatcher.indexer.last_check = None
    result = settle(dispatcher, session, force=False)
    assert result["error"] is None, result
    assert result["added_count"] == 1
    target.write_bytes(source)
    dispatcher.indexer.last_check = None
    result = settle(dispatcher, session, force=False)
    assert result["error"] is None, result
    assert result["added_count"] == 2


def test_indexer_waits_for_its_writer_before_rechecking_catalog_binding(library, monkeypatch):
    from playmemories_photo_manager.library import LibraryError, LibrarySession

    dispatcher, _, session, root, _ = library
    assert settle(dispatcher, session)["error"] is None
    indexer = dispatcher.indexer
    binding = LibrarySession.catalog_binding.fget

    def guarded_binding(owner):
        if owner is indexer.active and indexer.context and indexer.context["phase"] == "apply":
            raise LibraryError("busy")
        return binding(owner)

    monkeypatch.setattr(LibrarySession, "catalog_binding", property(guarded_binding))
    raster(root / "new.jpg")
    result = settle(dispatcher, session)
    assert result["error"] is None, result
    assert result["added_count"] == 1


def test_move_into_subfolder_keeps_asset_location_and_annotations(library):
    from playmemories_photo_manager.duplicates import find_exact_duplicates

    dispatcher, path, session, root, _ = library
    assert settle(dispatcher, session)["error"] is None
    first = root / "first.jpg"
    original = first.read_bytes()
    (root / "copy.jpg").write_bytes(original)
    assert settle(dispatcher, session)["error"] is None
    with connect(path) as connection:
        catalog = Catalog(connection)
        root_id = catalog.list_roots()[0].id
        original_location = next(
            location
            for location in catalog.list_root_locations(root_id)
            if location.normalized_relative_path == first.name
        )
        catalog.set_favorite(original_location.asset_id, True)
        album = catalog.create_album("Movimento")
        catalog.add_asset_to_album(album.id, original_location.asset_id)
    new_folder = root / "teste"
    new_folder.mkdir()
    first.rename(new_folder / first.name)

    dispatcher.indexer.last_check = None
    status = settle(dispatcher, session)
    assert status["error"] is None, status
    assert status["added_count"] == 1
    assert status["revision"] == 2
    with connect(path) as connection:
        catalog = Catalog(connection)
        locations = catalog.get_asset_locations(original_location.asset_id)
        live = next(location for location in locations if location.id == original_location.id)
        assert live.normalized_relative_path == "teste/first.jpg"
        assert live.availability == "present"
        history = next(location for location in locations if location.id != live.id)
        assert history.normalized_relative_path == "first.jpg" and history.availability == "missing"
        assert history.last_seen_at == original_location.last_seen_at
        assert catalog.get_annotation(live.asset_id).favorite
        assert [asset.id for asset in catalog.list_album_assets(album.id)] == [live.asset_id]
        assert len(catalog.list_assets()) == 2
        duplicate_result = find_exact_duplicates(connection)
        assert duplicate_result.coverage == "complete"
        assert {m.relative_path for m in duplicate_result.groups[0].members} == {
            "copy.jpg",
            "teste/first.jpg",
        }
    detail = dispatcher.request("asset.details", {"session_id": session, "asset_id": live.asset_id})
    assert detail["locations"][0]["relative_path"] == "teste/first.jpg"
    assert (new_folder / first.name).read_bytes() == original

    dispatcher.indexer.last_check = None
    assert settle(dispatcher, session)["revision"] == status["revision"]
    with connect(path) as connection:
        assert len(Catalog(connection).get_asset_locations(live.asset_id)) == 2


def test_already_indexed_destination_preserves_both_assets(library):
    from playmemories_photo_manager.duplicates import find_exact_duplicates

    dispatcher, path, session, root, _ = library
    assert settle(dispatcher, session)["error"] is None
    with connect(path) as connection:
        catalog = Catalog(connection)
        root_id = catalog.list_roots()[0].id
        old = catalog.list_root_locations(root_id)[0]
        other = catalog.create_asset("photo")
        new = catalog.register_location(
            other.id,
            root_id,
            "teste/first.jpg",
            last_seen_at="2026-11-11T00:00:00Z",
            filesystem_id=old.filesystem_id,
            observed_byte_size=old.observed_byte_size,
            observed_mtime_ns=old.observed_mtime_ns,
        )
    (root / "teste").mkdir()
    (root / "first.jpg").rename(root / new.normalized_relative_path)

    dispatcher.indexer.last_check = None
    status = settle(dispatcher, session)
    assert status["error"] is None, status
    assert status["added_count"] == 0
    with connect(path) as connection:
        catalog = Catalog(connection)
        assert len(catalog.list_assets()) == 2
        assert catalog.get_asset_locations(old.asset_id)[0].availability == "missing"
        assert catalog.get_asset_locations(other.id) == [new]
        result = find_exact_duplicates(connection)
        assert [(issue.kind, issue.relative_path) for issue in result.issues] == [
            ("location_unavailable", "first.jpg"),
        ]


def test_returning_to_the_original_path_restores_an_absent_location(library):
    dispatcher, path, session, root, _ = library
    assert settle(dispatcher, session)["error"] is None
    with connect(path) as connection:
        catalog = Catalog(connection)
        root_id = catalog.list_roots()[0].id
        original = catalog.list_root_locations(root_id)[0]

    detached = root.with_name("detached.jpg")
    (root / "first.jpg").rename(detached)
    dispatcher.indexer.last_check = None
    assert settle(dispatcher, session)["error"] is None
    with connect(path) as connection:
        assert (
            Catalog(connection).get_asset_locations(original.asset_id)[0].availability == "missing"
        )

    detached.rename(root / "first.jpg")
    dispatcher.indexer.last_check = None
    status = settle(dispatcher, session)
    assert status["error"] is None, status
    assert status["added_count"] == 0
    with connect(path) as connection:
        catalog = Catalog(connection)
        [location] = catalog.get_asset_locations(original.asset_id)
        assert (location.id, location.availability) == (original.id, "present")
        assert len(catalog.list_assets()) == 1
