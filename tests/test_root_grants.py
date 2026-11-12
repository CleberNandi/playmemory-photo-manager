"""Only synthetic roots/catalogs; root grants never open media contents."""

import os
import threading
import time
from uuid import uuid4

import pytest
from jpeg_fixtures import jpeg

from playmemories_photo_manager.catalog import Catalog
from playmemories_photo_manager.catalog.errors import CatalogStateConflictError
from playmemories_photo_manager.catalog_ingestion import root_grants as module
from playmemories_photo_manager.catalog_ingestion.preparation import PreparationError
from playmemories_photo_manager.catalog_ingestion.root_grants import RootGrantService
from playmemories_photo_manager.library import LibraryError, LibrarySession


@pytest.fixture
def setup(tmp_path):
    library = LibrarySession.create(tmp_path / "catalog.sqlite3")
    root = tmp_path / "photos"
    root.mkdir()
    service = RootGrantService(library, str(uuid4()), protected_paths=())
    yield library, service, root
    assert service.close()
    library.close()


def selection(service, root, **changes):
    return (
        dict(
            session_id=service.session_id,
            window_id=service.window_id,
            path=str(root),
            recursive=True,
            identity_reviewed=True,
        )
        | changes
    )


def preparation(service, grant, request_id=None, **changes):
    return (
        dict(
            session_id=service.session_id,
            window_id=service.window_id,
            root_grant_id=grant["root_grant_id"],
            recursive=True,
            client_request_id=request_id or str(uuid4()),
        )
        | changes
    )


def finish(service):
    deadline = time.monotonic() + 8
    while service.preparation.busy and time.monotonic() < deadline:
        service.tick()
        time.sleep(0.01)
    assert not service.preparation.busy
    return service.preparation._current


def test_registration_reuse_consumption_and_real_worker(setup):
    library, service, root = setup
    (root / "synthetic.jpg").write_bytes(jpeg())
    grant = service.select(selection(service, root))
    assert set(grant) == {"root_grant_id", "root_id", "expires_in_ms"}
    assert grant["expires_in_ms"] == 300000
    catalog = Catalog(library.query_connection)
    assert len(catalog.list_roots()) == 1
    assert catalog.list_roots()[0].id == grant["root_id"]
    assert library.query_connection.execute("SELECT COUNT(*) FROM asset").fetchone()[0] == 0
    assert library.query_connection.execute("SELECT COUNT(*) FROM file_location").fetchone()[0] == 0
    again = service.select(selection(service, root))
    assert again["root_id"] == grant["root_id"]
    assert service._grants[again["root_grant_id"]].diagnostics == ()
    params = preparation(service, grant)
    admitted = service.prepare(params)
    assert grant["root_grant_id"] not in service._grants
    assert service.prepare(params)["operation_id"] == admitted["operation_id"]
    assert finish(service).state == "completed"
    assert library.query_connection.execute("SELECT COUNT(*) FROM asset").fetchone()[0] == 0
    with pytest.raises(PreparationError, match="stale_grant"):
        service.prepare(preparation(service, grant))
    with pytest.raises(PreparationError, match="invalid_request"):
        service.prepare(params | {"root_grant_id": again["root_grant_id"]})


@pytest.mark.parametrize(
    "changes",
    [
        {"identity_reviewed": False},
        {"identity_reviewed": 1},
        {"recursive": False},
        {"recursive": 1},
        {"extra": True},
        {"path": "relative"},
        {"path": "/tmp/.."},
        {"path": "/tmp/"},
        {"path": "/tmp/./photos"},
        {"path": "/tmp/\0photos"},
    ],
)
def test_bad_selection_does_not_register(setup, changes):
    library, service, root = setup
    with pytest.raises(PreparationError, match="invalid_request"):
        service.select(selection(service, root, **changes))
    assert Catalog(library.query_connection).list_roots() == []
    assert not service._grants


def test_grants_are_scoped_expire_monotonically_and_release_fds(setup, monkeypatch):
    _library, service, root = setup
    before = len(os.listdir("/proc/self/fd"))
    grant = service.select(selection(service, root))
    for change in ({"session_id": str(uuid4())}, {"window_id": str(uuid4())}):
        with pytest.raises(PreparationError, match="stale_session"):
            service.prepare(preparation(service, grant, **change))
    expires = service._grants[grant["root_grant_id"]].expires
    original_clock = time.monotonic
    monkeypatch.setattr(module.time, "monotonic", lambda: expires)
    service.tick()
    with pytest.raises(PreparationError, match="stale_grant"):
        service.prepare(preparation(service, grant))
    assert len(os.listdir("/proc/self/fd")) == before
    monkeypatch.setattr(module.time, "monotonic", original_clock)


def test_symlinks_and_both_nested_root_directions_are_refused(setup):
    library, service, root = setup
    alias = root.with_name("alias")
    alias.symlink_to(root, target_is_directory=True)
    for path in (alias, alias / "child"):
        with pytest.raises(PreparationError, match="unsafe_location"):
            service.select(selection(service, path))
    service.select(selection(service, root))
    child = root / "child"
    child.mkdir()
    with pytest.raises(PreparationError, match="covered_subfolder"):
        service.select(selection(service, child))
    assert service.select({**selection(service, child), "return_covered_folder": True}) == {
        "covered_folder": {"root_id": service._roots()[0].id, "relative_path": "child"}
    }
    with library.command_connection() as connection:
        assert [item.normalized_path for item in Catalog(connection).list_roots()] == [str(root)]
    # A separate root with a registered nested path also blocks selection of its parent.
    outer = root.with_name("outer")
    nested = outer / "nested"
    nested.mkdir(parents=True)
    with library.command_connection() as connection:
        Catalog(connection).register_root("nested", str(nested))
    with pytest.raises(PreparationError, match="unsafe_location"):
        service.select(selection(service, outer))


def test_catalog_and_explicit_cache_cannot_be_contained_or_selected(setup):
    library, service, root = setup
    with pytest.raises(PreparationError, match="unsafe_location"):
        service.select(selection(service, root.parent))
    assert Catalog(library.query_connection).list_roots() == []
    # Catalog and photos sharing a parent is intentionally valid.
    service.select(selection(service, root))


def test_protected_cache_subtree(tmp_path):
    library = LibrarySession.create(tmp_path / "catalog.sqlite3")
    cache = tmp_path / "cache"
    child = cache / "nested"
    child.mkdir(parents=True)
    service = RootGrantService(library, str(uuid4()), protected_paths=(cache,))
    try:
        for root in (cache, child, tmp_path):
            with pytest.raises(PreparationError, match="unsafe_location"):
                service.select(selection(service, root))
        assert not Catalog(library.query_connection).list_roots()
    finally:
        service.close()
        library.close()


def test_same_session_root_replacement_is_not_silently_rebound(setup):
    _library, service, root = setup
    grant = service.select(selection(service, root))
    root.rename(root.with_name("retained"))
    root.mkdir()
    with pytest.raises(PreparationError, match="root_changed"):
        service.prepare(preparation(service, grant))
    with pytest.raises(PreparationError, match="root_changed"):
        service.select(selection(service, root))
    assert not service._grants


def test_relaunch_requires_review_and_records_missing_historical_identity(setup):
    library, service, root = setup
    grant = service.select(selection(service, root))
    assert service.close()
    library.close()
    path = root.parent / "catalog.sqlite3"
    with LibrarySession.open(path) as reopened:
        fresh = RootGrantService(reopened, str(uuid4()), protected_paths=())
        with pytest.raises(PreparationError, match="invalid_request"):
            fresh.select(selection(fresh, root, identity_reviewed=False))
        reviewed = fresh.select(selection(fresh, root))
        assert reviewed["root_id"] == grant["root_id"]
        assert fresh._grants[reviewed["root_grant_id"]].diagnostics == (
            "ROOT_IDENTITY_UNAVAILABLE",
        )
        assert fresh.close()


def test_atomic_root_registry_recheck_rolls_back_on_concurrent_change(setup, monkeypatch):
    library, service, root = setup
    original = Catalog.register_reviewed_root

    def race(catalog, *args, **kwargs):
        external = root.with_name("other")
        external.mkdir()
        catalog.register_root("external", str(external))
        return original(catalog, *args, **kwargs)

    monkeypatch.setattr(Catalog, "register_reviewed_root", race)
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(PreparationError, match="root_changed"):
        service.select(selection(service, root))
    assert len(os.listdir("/proc/self/fd")) == before
    roots = Catalog(library.query_connection).list_roots()
    assert len(roots) == 1 and roots[0].display_name == "external"
    assert not service._grants


def test_known_location_identity_checked_without_reading_contents(setup):
    library, service, root = setup
    file = root / "known.jpg"
    file.write_bytes(jpeg())
    with library.command_connection() as connection:
        catalog = Catalog(connection)
        known = catalog.register_root("known", str(root))
        asset = catalog.create_asset("photo")
        info = file.stat()
        catalog.register_location(
            asset.id,
            known.id,
            "known.jpg",
            last_seen_at="synthetic",
            filesystem_id=f"scanner:{info.st_dev}:{info.st_ino}",
            observed_byte_size=info.st_size,
            observed_mtime_ns=info.st_mtime_ns,
        )
    grant = service.select(selection(service, root))
    file.rename(root / "retained.jpg")
    file.write_bytes(jpeg())
    with pytest.raises(PreparationError, match="root_changed"):
        service.prepare(preparation(service, grant))


def test_closing_library_revokes_grants_and_waits_for_worker_reap(setup):
    library, service, root = setup
    grant = service.select(selection(service, root))
    service.prepare(preparation(service, grant))
    with pytest.raises(LibraryError, match="busy"):
        library.close()
    assert service._closed and not service._grants
    assert service.preparation.busy
    finish(service)
    library.close()
    with pytest.raises(PreparationError, match="stale_session"):
        service.select(selection(service, root))


def test_grant_budget_and_owner_thread(setup, monkeypatch):
    _library, service, root = setup
    monkeypatch.setattr(module, "MAX_GRANTS", 1)
    service.select(selection(service, root))
    with pytest.raises(PreparationError, match="resource_limit"):
        service.select(selection(service, root))
    errors = []

    def foreign():
        try:
            service.tick()
        except PreparationError as error:
            errors.append(error.code)

    thread = threading.Thread(target=foreign)
    thread.start()
    thread.join()
    assert errors == ["invalid_request"]


def test_catalog_register_reviewed_root_does_not_accept_stale_snapshot(setup):
    library, service, root = setup
    service.select(selection(service, root))
    with library.command_connection() as connection:
        with pytest.raises(CatalogStateConflictError):
            Catalog(connection).register_reviewed_root("stale", str(root), expected_roots=())
        assert not connection.in_transaction


def test_native_cancel_has_no_python_effect_and_close_releases_unconsumed_grants(setup):
    library, service, root = setup
    before = len(os.listdir("/proc/self/fd"))
    # Native cancellation is represented by not invoking select at all.
    assert not Catalog(library.query_connection).list_roots()
    service.select(selection(service, root))
    assert len(os.listdir("/proc/self/fd")) > before
    library.close()
    assert not service._grants and service._closed
    assert not service.preparation.busy


def test_selection_does_not_open_or_enumerate_media(setup, monkeypatch):
    _library, service, root = setup
    (root / "synthetic.jpg").write_bytes(jpeg())
    original = os.open

    def guarded(path, flags, *args, **kwargs):
        if str(path).endswith(".jpg"):
            pytest.fail("selection must not open a new media entry")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", guarded)
    service.select(selection(service, root))
    service.select(selection(service, root))


def test_changed_mount_alias_is_refused_without_registration(setup, monkeypatch):
    library, service, root = setup
    original = module._mount_id

    def mount(fd):
        actual = original(fd)
        return actual + 1 if os.readlink(f"/proc/self/fd/{fd}") == str(root) else actual

    monkeypatch.setattr(module, "_mount_id", mount)
    with pytest.raises(PreparationError, match="unsafe_location"):
        service.select(selection(service, root))
    assert not Catalog(library.query_connection).list_roots()


def test_descriptor_budget_failure_closes_candidate_handles(setup, monkeypatch):
    _library, service, root = setup
    initial = len(os.listdir("/proc/self/fd"))
    monkeypatch.setattr(module, "MAX_HELD_FDS", 2)
    with pytest.raises(PreparationError, match="resource_limit"):
        service.select(selection(service, root))
    assert len(os.listdir("/proc/self/fd")) == initial
    assert not service._grants


def test_changed_root_registry_after_grant_blocks_admission(setup):
    library, service, root = setup
    grant = service.select(selection(service, root))
    with library.command_connection() as connection:
        # External writer introduces a lexical overlap after grant issuance.
        Catalog(connection).register_root("nested", str(root / "nested"))
    with pytest.raises(PreparationError, match="unsafe_location"):
        service.prepare(preparation(service, grant))
    assert not service._grants and not service.preparation.busy


def test_worker_does_not_inherit_retained_grant_descriptors(setup):
    _library, service, root = setup
    grant = service.select(selection(service, root))
    held = service._grants[grant["root_grant_id"]].held
    descriptors = tuple(held.directories.fds)
    assert all(not os.get_inheritable(fd) for fd in descriptors)
    service.prepare(preparation(service, grant))
    assert not held.directories.fds
    assert finish(service).state == "completed"


def test_root_registry_budget_does_not_register_an_excess_root(setup, monkeypatch):
    library, service, root = setup
    monkeypatch.setattr(module, "MAX_ROOTS", 1)
    service.select(selection(service, root))
    other = root.with_name("other")
    other.mkdir()
    with pytest.raises(PreparationError, match="resource_limit"):
        service.select(selection(service, other))
    assert len(Catalog(library.query_connection).list_roots()) == 1


def test_post_commit_filesystem_change_does_not_issue_grant(setup, monkeypatch):
    library, service, root = setup
    original = Catalog.register_reviewed_root

    def race(catalog, *args, **kwargs):
        result = original(catalog, *args, **kwargs)
        root.rename(root.with_name("retained"))
        root.mkdir()
        return result

    monkeypatch.setattr(Catalog, "register_reviewed_root", race)
    with pytest.raises(PreparationError, match="root_changed"):
        service.select(selection(service, root))
    assert not service._grants and not service._bindings
    # Configuration committed before the external filesystem race can remain, without media.
    assert len(Catalog(library.query_connection).list_roots()) == 1
    assert library.query_connection.execute("SELECT COUNT(*) FROM asset").fetchone()[0] == 0


def test_admitted_job_survives_original_grant_deadline(setup):
    _library, service, root = setup
    grant = service.select(selection(service, root))
    retained = service._grants[grant["root_grant_id"]]
    service.prepare(preparation(service, grant))
    retained.expires = time.monotonic() - 1
    service.tick()
    assert finish(service).state == "completed"
