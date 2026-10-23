"""Connection and deliberately small SQL migration runner."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .tags import normalize_tag

_MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]+)_[a-z0-9_]+\.sql$")


class MigrationError(RuntimeError):
    """A migration set or migration execution is invalid."""


class IncompatibleSchemaError(MigrationError):
    """The database cannot be safely handled by this application version."""


def _is_uuid(value: object) -> int:
    if not isinstance(value, str):
        return 0
    try:
        return int(str(uuid.UUID(value)) == value)
    except (ValueError, AttributeError):
        return 0


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


def connect(path: str | Path) -> sqlite3.Connection:
    """Open an operational connection with referential integrity enabled."""
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.create_function("is_uuid", 1, _is_uuid, deterministic=True)
    connection.create_function("normalize_tag", 1, normalize_tag, deterministic=True)
    connection.execute("PRAGMA foreign_keys = ON")
    enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    if enabled != 1:
        connection.close()
        raise RuntimeError("SQLite foreign key enforcement could not be enabled")
    return connection


def _load_migrations(directory: Path | None = None) -> list[Migration]:
    root = directory or Path(str(files(__package__).joinpath("migrations")))
    migrations: list[Migration] = []
    for path in sorted(root.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"unknown migration filename: {path.name}")
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=int(match.group("version")),
                name=path.name,
                sql=sql,
                checksum=hashlib.sha256(sql.encode()).hexdigest(),
            )
        )
    versions = [migration.version for migration in migrations]
    if versions != list(range(1, len(migrations) + 1)):
        raise MigrationError(f"migration versions must be contiguous from 1: {versions}")
    return migrations


def _migration_history(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'schema_migration'"
    ).fetchone()
    if not exists:
        return []
    return connection.execute(
        "SELECT version, name, checksum FROM schema_migration ORDER BY version"
    ).fetchall()


def _validate_state(connection: sqlite3.Connection, migrations: list[Migration]) -> int:
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    if current > len(migrations):
        raise IncompatibleSchemaError(
            f"database schema version {current} is newer than supported version {len(migrations)}"
        )
    history = _migration_history(connection)
    if current == 0 and history:
        raise IncompatibleSchemaError("migration history exists while user_version is zero")
    if current > 0 and len(history) != current:
        raise IncompatibleSchemaError("user_version and migration history disagree")
    for row, expected in zip(history, migrations[:current], strict=True):
        if (row["version"], row["name"], row["checksum"]) != (
            expected.version,
            expected.name,
            expected.checksum,
        ):
            raise IncompatibleSchemaError(f"migration {row['version']} is unknown or was modified")
    return current


def apply_migrations(
    connection: sqlite3.Connection, *, migration_directory: Path | None = None
) -> int:
    """Apply pending migrations, each atomically with its history record."""
    migrations = _load_migrations(migration_directory)
    current = _validate_state(connection, migrations)
    for migration in migrations[current:]:
        escaped_name = migration.name.replace("'", "''")
        script = "\n".join(
            (
                "BEGIN IMMEDIATE;",
                migration.sql,
                "INSERT INTO schema_migration(version, name, checksum) "
                f"VALUES ({migration.version}, '{escaped_name}', '{migration.checksum}');",
                f"PRAGMA user_version = {migration.version};",
                "COMMIT;",
            )
        )
        try:
            connection.executescript(script)
        except sqlite3.Error as error:
            if connection.in_transaction:
                connection.rollback()
            raise MigrationError(f"migration {migration.name} failed") from error
    return len(migrations)


def initialize_database(
    path: str | Path, *, migration_directory: Path | None = None
) -> sqlite3.Connection:
    """Open a database, migrate it to the supported version, and return it."""
    connection = connect(path)
    try:
        apply_migrations(connection, migration_directory=migration_directory)
    except Exception:
        connection.close()
        raise
    return connection


def execute_statements(
    connection: sqlite3.Connection, statements: Iterable[tuple[str, tuple]]
) -> None:
    """Execute a small unit of application work atomically."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        for sql, parameters in statements:
            connection.execute(sql, parameters)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
