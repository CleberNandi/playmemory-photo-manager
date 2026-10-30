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


def connect(path: str | Path, *, uri: bool = False, timeout: float = 5.0) -> sqlite3.Connection:
    """Open an operational connection with referential integrity enabled."""
    connection = sqlite3.connect(path, isolation_level=None, uri=uri, timeout=timeout)
    connection.row_factory = sqlite3.Row
    connection.create_function("is_uuid", 1, _is_uuid, deterministic=True)
    connection.create_function("normalize_tag", 1, normalize_tag, deterministic=True)
    connection.execute("PRAGMA foreign_keys = ON")
    enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    if enabled != 1:
        connection.close()
        raise RuntimeError("SQLite foreign key enforcement could not be enabled")
    return connection


class UpgradeRequiredError(IncompatibleSchemaError):
    """A recognized older catalog requires an explicit future upgrade."""


def validate_database(connection: sqlite3.Connection) -> None:
    """Validate the current schema and data without migrations or persistent writes.

    Compare stored DDL with a reference built only in memory. This deliberately rejects
    edited DDL, including weakened constraints, extra triggers and missing indexes.
    The caller owns the connection and must install the managed UDFs first.
    """
    if sqlite3.sqlite_version_info < (3, 37, 0):
        raise IncompatibleSchemaError("SQLite 3.37 or newer is required")
    if connection.in_transaction:
        raise MigrationError("validation requires no active transaction")
    # This validates the supplied connection; only the lifecycle's descriptor
    # preflight can reject persisted WAL before SQLite has touched auxiliaries.
    if connection.execute("PRAGMA journal_mode").fetchone()[0] not in ("delete", "memory"):
        raise IncompatibleSchemaError("journal mode is not supported by the library lifecycle")
    reference = initialize_database(":memory:")
    try:
        connection.execute("BEGIN")
        migrations = _load_migrations()
        current = _validate_state(connection, migrations)
        if current == 0:
            raise IncompatibleSchemaError("not a catalog")
        if current < len(migrations):
            raise UpgradeRequiredError("explicit upgrade required")
        sql = (
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
        actual = [tuple(row) for row in connection.execute(sql)]
        expected = [tuple(row) for row in reference.execute(sql)]
        if actual != expected:
            raise IncompatibleSchemaError("catalog structure differs from supported schema")
        # Inspect SQLite's parsed structures as well as the stored DDL text.
        for row in reference.execute("SELECT name FROM sqlite_schema WHERE type = 'table'"):
            table = row[0]
            for pragma in ("table_xinfo", "foreign_key_list", "index_list"):
                statement = f'PRAGMA {pragma}("{table}")'
                if [tuple(r) for r in connection.execute(statement)] != [
                    tuple(r) for r in reference.execute(statement)
                ]:
                    raise IncompatibleSchemaError("catalog table structure differs")
        for row in reference.execute("SELECT name FROM sqlite_schema WHERE type = 'index'"):
            statement = f'PRAGMA index_xinfo("{row[0]}")'
            if [tuple(r) for r in connection.execute(statement)] != [
                tuple(r) for r in reference.execute(statement)
            ]:
                raise IncompatibleSchemaError("catalog index structure differs")
        if [row[0] for row in connection.execute("PRAGMA integrity_check")] != ["ok"]:
            raise IncompatibleSchemaError("catalog integrity failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise IncompatibleSchemaError("catalog referential integrity failed")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise IncompatibleSchemaError("foreign keys are disabled")
    finally:
        if connection.in_transaction:
            connection.rollback()
        reference.close()


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
    if connection.in_transaction:
        raise MigrationError("migrations require a connection with no active transaction")
    migrations = _load_migrations(migration_directory)
    current = _validate_state(connection, migrations)
    for migration in migrations[current:]:
        statements = _split_sql_statements(migration.sql)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.set_authorizer(_deny_transaction_control)
            for statement in statements:
                connection.execute(statement)
            connection.set_authorizer(None)
            connection.execute(
                "INSERT INTO schema_migration(version, name, checksum) VALUES (?, ?, ?)",
                (migration.version, migration.name, migration.checksum),
            )
            connection.execute(f"PRAGMA user_version = {migration.version}")
            connection.commit()
        except sqlite3.Error as error:
            connection.set_authorizer(None)
            if connection.in_transaction:
                connection.rollback()
            raise MigrationError(f"migration {migration.name} failed") from error
    return len(migrations)


def _split_sql_statements(script: str) -> list[str]:
    """Split SQL without breaking compound statements such as triggers."""
    statements: list[str] = []
    pending: list[str] = []
    for character in script:
        pending.append(character)
        candidate = "".join(pending)
        if character == ";" and sqlite3.complete_statement(candidate):
            statements.append(candidate)
            pending.clear()
    if "".join(pending).strip():
        raise MigrationError("migration contains an incomplete SQL statement")
    return statements


def _deny_transaction_control(
    action: int, _arg1: str | None, _arg2: str | None, _database: str | None, _trigger: str | None
) -> int:
    """Keep migration files from escaping the runner-owned transaction."""
    if action in (sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


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
