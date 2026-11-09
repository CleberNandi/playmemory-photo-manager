"""Disposable Linux pixel decoder: inherited read-only fd, bounded memory/CPU/output."""

from __future__ import annotations

import ctypes
import io
import os
import resource
import signal
import sys
import warnings


def main():
    if len(sys.argv) != 4 or sys.platform != "linux":
        return 2
    fd, parent, variant = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != parent:
        return 2
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from PIL import Image, ImageOps

    from ..catalog_ingestion.images import FORMATS, MAX_PIXELS

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    try:
        with (
            os.fdopen(fd, "rb") as source,
            Image.open(source, formats=[f.upper() for f in FORMATS]) as image,
        ):
            if image.width * image.height > MAX_PIXELS:
                return 2
            # First frame/page only; no external program or original path enters the decoder.
            image.seek(0)
            image.load()
            upright = ImageOps.exif_transpose(image).convert("RGB")
            output = io.BytesIO()
            if variant == "grid":
                upright.thumbnail((256, 160))
                canvas = Image.new("RGB", (256, 160), "#e5e7eb")
                canvas.paste(upright, ((256 - upright.width) // 2, (160 - upright.height) // 2))
                canvas.save(output, format="PNG")
            elif variant == "preview":
                upright.thumbnail((1280, 960))
                upright.save(output, format="JPEG", quality=65)
            else:
                return 2
            data = output.getvalue()
            if len(data) > 160 * 1024:
                return 2
            sys.stdout.buffer.write(data)
            return 0
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
