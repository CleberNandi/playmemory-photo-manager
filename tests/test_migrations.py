from __future__ import annotations

import sqlite3

import pytest

from playmemories_photo_manager.catalog.database import (
    IncompatibleSchemaError,
    MigrationError,
    apply_migrations,
    connect,
    initialize_database,
)


def test_new_database_is_created_at_latest_version(tmp_path) -> None:
    connection = initialize_database(tmp_path / "new.sqlite3")
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert [tuple(row) for row in connection.execute("SELECT version FROM schema_migration")] == [
        (1,)
    ]
    assert connection.execute(
        "SELECT strict FROM pragma_table_list WHERE name = 'asset'"
    ).fetchone()[0]
    connection.close()


def test_foreign_keys_are_enabled_on_every_managed_connection(tmp_path) -> None:
    connection = connect(tmp_path / "catalog.sqlite3")
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    connection.close()


def test_reexecution_does_not_reapply_migration(tmp_path) -> None:
    path = tmp_path / "catalog.sqlite3"
    first = initialize_database(path)
    applied_at = first.execute("SELECT applied_at FROM schema_migration").fetchone()[0]
    first.close()
    second = initialize_database(path)
    assert second.execute("SELECT count(*) FROM schema_migration").fetchone()[0] == 1
    assert second.execute("SELECT applied_at FROM schema_migration").fetchone()[0] == applied_at
    second.close()


def test_migrations_are_applied_in_numeric_order(tmp_path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_first.sql").write_text(
        """CREATE TABLE schema_migration(
            version INTEGER PRIMARY KEY, name TEXT UNIQUE, checksum TEXT,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE trace(value TEXT NOT NULL);
        INSERT INTO trace(value) VALUES ('first');
        """,
        encoding="utf-8",
    )
    (migrations / "002_second.sql").write_text(
        "INSERT INTO trace(value) SELECT value || '-then-second' FROM trace;",
        encoding="utf-8",
    )
    connection = connect(tmp_path / "ordered.sqlite3")
    assert apply_migrations(connection, migration_directory=migrations) == 2
    assert [row[0] for row in connection.execute("SELECT value FROM trace ORDER BY rowid")] == [
        "first",
        "first-then-second",
    ]
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    connection.close()


def test_failed_migration_is_atomic(tmp_path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_broken.sql").write_text(
        "CREATE TABLE schema_migration(version INTEGER PRIMARY KEY, name TEXT, checksum TEXT);\n"
        "CREATE TABLE partial(value TEXT);\n"
        "THIS IS NOT SQL;\n",
        encoding="utf-8",
    )
    connection = connect(tmp_path / "broken.sqlite3")
    with pytest.raises(MigrationError):
        apply_migrations(connection, migration_directory=migrations)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    assert (
        connection.execute(
            "SELECT count(*) FROM sqlite_schema WHERE name IN ('partial', 'schema_migration')"
        ).fetchone()[0]
        == 0
    )
    connection.close()


def test_newer_schema_version_is_rejected(tmp_path) -> None:
    path = tmp_path / "future.sqlite3"
    connection = connect(path)
    connection.execute("PRAGMA user_version = 99")
    connection.close()
    with pytest.raises(IncompatibleSchemaError, match="newer"):
        initialize_database(path)


def test_modified_applied_migration_is_rejected(tmp_path) -> None:
    path = tmp_path / "changed.sqlite3"
    connection = initialize_database(path)
    connection.execute("UPDATE schema_migration SET checksum = ?", ("0" * 64,))
    connection.close()
    with pytest.raises(IncompatibleSchemaError, match="modified"):
        initialize_database(path)


def test_unknown_migration_filename_is_rejected(tmp_path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "surprise.sql").write_text("SELECT 1;", encoding="utf-8")
    connection = connect(tmp_path / "catalog.sqlite3")
    with pytest.raises(MigrationError, match="unknown migration"):
        apply_migrations(connection, migration_directory=migrations)
    connection.close()


def test_integrity_checks_pass(database: sqlite3.Connection) -> None:
    assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert database.execute("PRAGMA foreign_key_check").fetchall() == []


def test_invalid_foreign_key_is_rejected(database: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO album_asset(album_id, asset_id) VALUES ('missing-album', 'missing-asset')"
        )
