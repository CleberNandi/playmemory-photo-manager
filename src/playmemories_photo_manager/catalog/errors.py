"""Stable application errors for catalog operations."""


class CatalogError(Exception):
    """Base class for expected catalog failures."""


class InvalidInputError(CatalogError, ValueError):
    """A caller supplied a value outside the public contract."""


class NotFoundError(CatalogError):
    """A requested entity does not exist."""


class DuplicateAssociationError(CatalogError):
    """A many-to-many association already exists."""


class UniquenessConflictError(CatalogError):
    """A unique domain value is already owned by another entity."""


class InvalidReferenceError(CatalogError):
    """An operation refers to an entity that does not exist."""


class InvariantViolationError(CatalogError):
    """An operation violates a domain invariant."""


class PersistenceError(CatalogError):
    """SQLite failed in a way not represented by a more specific error."""


class CatalogStateConflictError(CatalogError):
    """Current catalog state conflicts with a previously planned registration."""

    def __init__(self, message: str, *, relative_paths: tuple[str, ...]) -> None:
        super().__init__(message)
        self.relative_paths = relative_paths
