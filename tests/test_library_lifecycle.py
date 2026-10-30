"""Only disposable catalogs, no media access."""

import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from playmemories_photo_manager.catalog.database import (
    IncompatibleSchemaError,
    initialize_database,
    validate_database,
)
from playmemories_photo_manager.library import (
    LibraryError,
    LibraryLifecycle,
    LibrarySession,
    lifecycle,
)


def test_create_reopen_separate_connections_and_close(tmp_path):
    path = tmp_path / "catálogo #?.sqlite3"
    with LibrarySession.create(path) as session:
        first = session.descriptor.session_id
        query = session.query_connection
        with pytest.raises(sqlite3.OperationalError):
            query.execute("CREATE TABLE forbidden(x)")
        with session.command_connection() as command:
            assert command is not query
            command.execute("BEGIN IMMEDIATE")
            command.execute(
                "INSERT INTO album(id,name) VALUES (?,?)",
                ("1c7ca260-2e26-4c60-9de1-acd869856608", "test"),
            )
            command.commit()
        assert query.execute("SELECT name FROM album").fetchone()[0] == "test"
    with pytest.raises(sqlite3.ProgrammingError):
        query.execute("SELECT 1")
    before = path.read_bytes()
    with LibrarySession.open(path) as reopened:
        assert reopened.descriptor.session_id != first
    assert path.read_bytes() == before
    assert path.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


def test_missing_and_exclusive(tmp_path):
    path = tmp_path / "catalog"
    with pytest.raises(LibraryError, match="not_found"):
        LibrarySession.open(path)
    assert not path.exists()
    with LibrarySession.create(path):
        before = path.read_bytes()
        with pytest.raises(LibraryError, match="unsafe_location"):
            LibrarySession.create(path)
        assert path.read_bytes() == before


@pytest.mark.parametrize("content", [b"", b"not sqlite"])
def test_invalid_bytes_unchanged(tmp_path, content):
    path = tmp_path / "catalog"
    path.write_bytes(content)
    with pytest.raises(LibraryError):
        LibrarySession.open(path)
    assert path.read_bytes() == content


@pytest.mark.parametrize("kind", ["old", "future", "checksum", "index", "trigger", "foreign_key"])
def test_invalid_schema_or_data_never_upgraded(tmp_path, kind):
    path = tmp_path / "catalog"
    db = initialize_database(path)
    if kind == "old":
        db.execute("DELETE FROM schema_migration WHERE version = 2")
        db.execute("PRAGMA user_version = 1")
    elif kind == "future":
        db.execute("PRAGMA user_version = 3")
    elif kind == "checksum":
        db.execute("UPDATE schema_migration SET checksum = ? WHERE version = 1", ("0" * 64,))
    elif kind == "index":
        db.execute("DROP INDEX uq_file_location_active_path")
    elif kind == "trigger":
        db.execute("DROP TRIGGER prevent_asset_id_update")
    else:
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("INSERT INTO album_asset(album_id,asset_id) VALUES ('a','b')")
    db.close()
    before = path.read_bytes()
    expected = "upgrade_required" if kind == "old" else "incompatible"
    with pytest.raises(LibraryError, match=expected):
        LibrarySession.open(path)
    assert path.read_bytes() == before


def test_validator_no_persistent_statements():
    db = initialize_database(":memory:")
    statements = []
    db.set_trace_callback(statements.append)
    validate_database(db)
    assert not db.in_transaction
    assert not any(
        s.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")) for s in statements
    )
    db.close()


@pytest.mark.parametrize("kind", ["file_link", "ancestor_link", "hardlink", "fifo", "journal_link"])
def test_unsafe_locations(tmp_path, kind):
    actual = tmp_path / "actual"
    actual.mkdir()
    path = actual / "catalog"
    with LibrarySession.create(path):
        pass
    target = path
    if kind == "file_link":
        target = tmp_path / "link"
        target.symlink_to(path)
    elif kind == "ancestor_link":
        link = tmp_path / "link"
        link.symlink_to(actual, target_is_directory=True)
        target = link / "catalog"
    elif kind == "hardlink":
        os.link(path, tmp_path / "alias")
    elif kind == "fifo":
        target = tmp_path / "fifo"
        os.mkfifo(target)
    else:
        Path(str(path) + "-journal").symlink_to(tmp_path / "untouched")
    before = path.read_bytes()
    with pytest.raises(LibraryError, match="unsafe_location"):
        LibrarySession.open(target)
    assert path.read_bytes() == before


def test_swap_during_sqlite_open_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "catalog"
    other = tmp_path / "other"
    for candidate in (path, other):
        with LibrarySession.create(candidate):
            pass
    original_connect = lifecycle.connect

    def swap(*args, **kwargs):
        other.replace(path)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(lifecycle, "connect", swap)
    with pytest.raises(LibraryError, match="unsafe_location"):
        LibrarySession.open(path)


def test_closed_nested_rollback_and_busy(tmp_path):
    path = tmp_path / "catalog"
    session = LibrarySession.create(path)
    with session.command_connection() as command:
        with pytest.raises(LibraryError, match="busy"), session.command_connection():
            pass
        with pytest.raises(LibraryError, match="busy"):
            session.close()
        command.execute("BEGIN IMMEDIATE")
        command.execute("DELETE FROM schema_migration")
    # Closing an unfinished command rolls it back.
    assert (
        session.query_connection.execute("SELECT count(*) FROM schema_migration").fetchone()[0] == 2
    )
    lock = sqlite3.connect(path, isolation_level=None)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(LibraryError, match="busy"), session.command_connection():
            pass
    finally:
        lock.rollback()
        lock.close()
    session.close()
    session.close()
    with pytest.raises(LibraryError, match="stale_session"):
        _ = session.query_connection


def test_failure_keeps_new_artifact_and_does_not_activate(tmp_path, monkeypatch):
    def fail(_connection):
        raise RuntimeError("private bootstrap detail")

    monkeypatch.setattr(lifecycle, "apply_migrations", fail)
    path = tmp_path / "catalog"
    with pytest.raises(LibraryError, match="internal_error") as failure:
        LibrarySession.create(path)
    assert str(failure.value) == "internal_error"
    assert path.exists()


def test_catalog_inside_registered_root_rejected_without_observation(tmp_path):
    path = tmp_path / "catalog"
    db = initialize_database(path)
    db.execute(
        "INSERT INTO library_root(id,display_name,normalized_path) VALUES (?,?,?)",
        ("1c7ca260-2e26-4c60-9de1-acd869856608", "synthetic", str(tmp_path)),
    )
    db.close()
    with pytest.raises(LibraryError, match="unsafe_location"):
        LibrarySession.open(path)


def test_known_media_scope_rejected_before_creation(tmp_path):
    with pytest.raises(LibraryError, match="unsafe_location"):
        LibrarySession.create(tmp_path / "catalog", known_media_roots=(tmp_path,))
    assert not list(tmp_path.iterdir())


def test_lifecycle_preserves_previous_on_failure_and_closes_on_swap(tmp_path):
    owner = LibraryLifecycle()
    assert owner.active is None
    first = owner.create(tmp_path / "first")
    old = owner.active
    generation = owner.generation
    with pytest.raises(LibraryError, match="not_found"):
        owner.open(tmp_path / "missing")
    assert owner.active is old
    assert owner.generation == generation
    assert old.descriptor == first
    second = owner.create(tmp_path / "second")
    assert second.session_id != first.session_id
    assert owner.generation > generation
    with pytest.raises(LibraryError, match="stale_session"):
        _ = old.query_connection
    owner.close()
    assert owner.active is None


def test_clean_wal_rejected_before_sqlite_and_without_auxiliaries(tmp_path, monkeypatch):
    path = tmp_path / "catalog"
    db = initialize_database(path)
    assert db.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    db.close()
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert set(before) == {path.name}

    def forbidden_connect(*_args, **_kwargs):
        pytest.fail("WAL must be rejected before SQLite opens the file")

    monkeypatch.setattr(lifecycle, "connect", forbidden_connect)
    with pytest.raises(LibraryError, match="incompatible"):
        LibrarySession.open(path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_validator_rejects_wal_without_changing_journal_mode(tmp_path):
    db = initialize_database(tmp_path / "catalog")
    try:
        db.execute("PRAGMA journal_mode = WAL")
        with pytest.raises(IncompatibleSchemaError):
            validate_database(db)
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert not db.in_transaction
    finally:
        db.close()


@pytest.mark.parametrize("registered", [False, True])
def test_media_subdirectory_does_not_contain_catalog(tmp_path, registered):
    # The catalog file and its auxiliaries are outside photos, even though their
    # common parent contains photos. No recursive catalog-directory scope exists.
    path = tmp_path / "catalog"
    root = tmp_path / "photos"
    root.mkdir()
    if registered:
        db = initialize_database(path)
        db.execute(
            "INSERT INTO library_root(id,display_name,normalized_path) VALUES (?,?,?)",
            ("1c7ca260-2e26-4c60-9de1-acd869856608", "synthetic", str(root)),
        )
        db.close()
        with LibrarySession.open(path):
            pass
    else:
        with LibrarySession.create(path, known_media_roots=(root,)):
            pass
    assert not list(root.iterdir())


def test_wrong_thread_does_not_touch_connection(tmp_path):
    with (
        LibrarySession.create(tmp_path / "catalog") as session,
        ThreadPoolExecutor(1) as executor,
    ):
        future = executor.submit(lambda: session.query_connection)
        with pytest.raises(LibraryError, match="invalid_request"):
            future.result()


def test_concurrent_creation_has_one_winner(tmp_path):
    path = tmp_path / "catalog"

    def attempt():
        try:
            with LibrarySession.create(path):
                return "created"
        except LibraryError as error:
            return error.code

    with ThreadPoolExecutor(2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes) == ["created", "unsafe_location"]


def test_permission_denial_is_real_even_when_runner_is_root(tmp_path):
    # Drop privilege when allowed; capability-free root can also be denied.
    # Independently prove the OS denies access before exercising the lifecycle.
    path = tmp_path / "catalog"
    with LibrarySession.create(path):
        pass
    path.chmod(0)
    code = """
import os
import sys
from pathlib import Path
from playmemories_photo_manager.library import LibraryError, LibrarySession
if os.geteuid() == 0:
    try:
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
    except PermissionError:
        pass
try:
    descriptor = os.open(sys.argv[1], os.O_RDONLY)
except PermissionError:
    pass
else:
    os.close(descriptor)
    raise AssertionError('fixture did not deny actual OS access')
try:
    LibrarySession.open(Path(sys.argv[1]))
except LibraryError as error:
    assert error.code == 'permission_denied', error.code
else:
    raise AssertionError('access unexpectedly granted')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path)],
        env={**os.environ, "PYTHONPATH": str(Path(lifecycle.__file__).parents[2])},
        capture_output=True,
        text=True,
        timeout=10,
    )
    path.chmod(0o600)
    assert result.returncode == 0, result.stderr


def test_unwitnessed_sqlite_descriptor_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "catalog"
    with LibrarySession.create(path):
        pass
    monkeypatch.setattr(lifecycle.os, "listdir", lambda _: [])
    with pytest.raises(LibraryError, match="unsafe_location"):
        LibrarySession.open(path)


def test_regular_pending_journal_refused_unchanged(tmp_path):
    path = tmp_path / "catalog"
    with LibrarySession.create(path):
        pass
    journal = Path(str(path) + "-journal")
    journal.write_bytes(b"synthetic pending journal")
    before = path.read_bytes()
    with pytest.raises(LibraryError, match="busy"):
        LibrarySession.open(path)
    assert path.read_bytes() == before
    assert journal.read_bytes() == b"synthetic pending journal"


def test_wrong_sqlite_inode_rejected_even_when_selected_path_restored(tmp_path, monkeypatch):
    path = tmp_path / "catalog"
    other = tmp_path / "other"
    saved = tmp_path / "saved"
    for candidate in (path, other):
        with LibrarySession.create(candidate):
            pass
    original_connect = lifecycle.connect

    def swap_and_restore(*args, **kwargs):
        path.rename(saved)
        other.rename(path)
        try:
            return original_connect(*args, **kwargs)
        finally:
            path.rename(other)
            saved.rename(path)

    monkeypatch.setattr(lifecycle, "connect", swap_and_restore)
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(LibraryError, match="unsafe_location"):
        LibrarySession.open(path)
    assert len(os.listdir("/proc/self/fd")) == before


def test_same_asset_uuid_does_not_cross_libraries(tmp_path):
    owner = LibraryLifecycle()
    asset_id = "1c7ca260-2e26-4c60-9de1-acd869856608"
    for filename, kind in (("first", "photo"), ("second", "video")):
        owner.create(tmp_path / filename)
        with owner.active.command_connection() as command:
            command.execute("BEGIN IMMEDIATE")
            command.execute("INSERT INTO asset(id,kind) VALUES (?,?)", (asset_id, kind))
            command.commit()
    owner.open(tmp_path / "first")
    assert owner.active.query_connection.execute("SELECT kind FROM asset").fetchone()[0] == "photo"
    owner.open(tmp_path / "second")
    assert owner.active.query_connection.execute("SELECT kind FROM asset").fetchone()[0] == "video"
    owner.close()
