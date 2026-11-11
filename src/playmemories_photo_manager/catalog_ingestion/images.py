"""Bounded maintained raster header verification, used only in supervised workers."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

PROFILE = "raster_header_v1"
FORMATS = {
    "jpeg": ("image/jpeg", (".jpg", ".jpeg", ".jpe")),
    "png": ("image/png", (".png",)),
    "webp": ("image/webp", (".webp",)),
    "gif": ("image/gif", (".gif",)),
    "bmp": ("image/bmp", (".bmp", ".dib")),
    "tiff": ("image/tiff", (".tif", ".tiff")),
    "avif": ("image/avif", (".avif",)),
    "ico": ("image/x-icon", (".ico",)),
}
EXTENSIONS = frozenset(ext for _, extensions in FORMATS.values() for ext in extensions)
MAX_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 40_000_000


@dataclass(frozen=True, slots=True)
class ImageInspection:
    reason: str
    detected_format: str | None


def inspect_image(source, size, *, checkpoint, decode=False):
    from PIL import Image, UnidentifiedImageError

    checkpoint()
    if not size:
        return ImageInspection("empty_file", None)
    if size > MAX_BYTES:
        return ImageInspection("byte_limit_exceeded", None)
    detected = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            source.seek(0)
            with Image.open(source, formats=[name.upper() for name in FORMATS]) as image:
                detected = image.format.lower()
                width, height = image.size
                if not 0 < width <= 16384 or not 0 < height <= 16384 or width * height > MAX_PIXELS:
                    return ImageInspection("dimension_limit_exceeded", detected)
                if decode:
                    image.load()
                else:
                    image.verify()
            checkpoint()
            return ImageInspection("eligible_image", detected)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return ImageInspection("dimension_limit_exceeded", detected)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return ImageInspection("invalid_image", detected)
