"""Stable failures exposed by the gallery read model."""


class GalleryError(Exception):
    """Base class for expected gallery failures."""


class InvalidGalleryQueryError(GalleryError, ValueError):
    """A gallery query or identifier is outside the public contract."""


class InvalidCursorError(InvalidGalleryQueryError):
    """A cursor is malformed, incompatible, or was modified."""


class AssetNotFoundError(GalleryError):
    """The requested Asset does not exist."""


class CatalogReadError(GalleryError):
    """Persisted catalog data cannot be projected safely."""


class ThumbnailError(GalleryError):
    """Base class for synthetic thumbnail failures."""


class InvalidThumbnailError(ThumbnailError, ValueError):
    """A thumbnail fixture or public identifier is invalid."""


class ThumbnailNotFoundError(ThumbnailError):
    """A thumbnail identifier is unknown or its cache file is absent."""


class UnsafeThumbnailPathError(ThumbnailError):
    """The cache cannot be opened with the required confinement guarantees."""


class ThumbnailTooLargeError(ThumbnailError):
    """A cache entry exceeds the configured read limit."""


class UnsupportedThumbnailPlatformError(ThumbnailError):
    """The platform lacks the POSIX primitives required by this store."""
