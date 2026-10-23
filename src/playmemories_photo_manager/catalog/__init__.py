"""SQLite catalog adapter."""

from .database import (
    IncompatibleSchemaError,
    MigrationError,
    connect,
    initialize_database,
)
from .errors import (
    CatalogError,
    DuplicateAssociationError,
    InvalidInputError,
    InvalidReferenceError,
    InvariantViolationError,
    NotFoundError,
    PersistenceError,
    UniquenessConflictError,
)
from .models import (
    Album,
    Annotation,
    Asset,
    AssetKind,
    EntryType,
    FileLocation,
    HashState,
    LibraryRoot,
    LocationAvailability,
    RootAvailability,
    Tag,
)
from .service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Catalog
from .tags import create_tag, normalize_tag

__all__ = [
    "Album",
    "Annotation",
    "Asset",
    "AssetKind",
    "Catalog",
    "CatalogError",
    "DEFAULT_PAGE_SIZE",
    "DuplicateAssociationError",
    "EntryType",
    "FileLocation",
    "HashState",
    "IncompatibleSchemaError",
    "InvalidInputError",
    "InvalidReferenceError",
    "InvariantViolationError",
    "LibraryRoot",
    "LocationAvailability",
    "MAX_PAGE_SIZE",
    "MigrationError",
    "NotFoundError",
    "PersistenceError",
    "RootAvailability",
    "Tag",
    "UniquenessConflictError",
    "connect",
    "create_tag",
    "initialize_database",
    "normalize_tag",
]
