"""SQLite catalog adapter."""

from .database import (
    IncompatibleSchemaError,
    MigrationError,
    connect,
    initialize_database,
)
from .tags import create_tag, normalize_tag

__all__ = [
    "IncompatibleSchemaError",
    "MigrationError",
    "connect",
    "create_tag",
    "initialize_database",
    "normalize_tag",
]
