"""Disposable full-resolution encoder. Only inherited input/output descriptors are used."""

import ctypes
import os
import resource
import signal
import struct
import sys
import warnings


def main():
    if len(sys.argv) != 5 or sys.platform != "linux":
        return 2
    source, destination, parent, angle = map(int, sys.argv[1:])
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != parent:
        return 2
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from PIL import Image, ImageOps, PngImagePlugin

    Image.MAX_IMAGE_PIXELS = 40_000_000
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    try:
        with os.fdopen(source, "rb") as reader, Image.open(reader) as image:
            if image.format not in ("PNG", "JPEG") or getattr(image, "n_frames", 1) != 1:
                return 3
            if not 0 < image.width * image.height <= 40_000_000 or angle not in (90, 180, 270):
                return 3
            format = image.format
            image.load()
            upright = ImageOps.exif_transpose(image)
            rotated = upright.transpose(
                {
                    90: Image.Transpose.ROTATE_270,
                    180: Image.Transpose.ROTATE_180,
                    270: Image.Transpose.ROTATE_90,
                }[angle]
            )
            exif = upright.getexif()
            if exif:
                exif[274] = 1
                if 40962 in exif:
                    exif[40962] = rotated.width
                if 40963 in exif:
                    exif[40963] = rotated.height
            options = {}
            if exif:
                options["exif"] = exif.tobytes()
            if "icc_profile" in image.info:
                options["icc_profile"] = image.info["icc_profile"]
            if format == "PNG":
                text = PngImagePlugin.PngInfo()
                for key, value in getattr(image, "text", {}).items():
                    if isinstance(value, str):
                        text.add_itxt(key, value)
                if "gamma" in image.info:
                    text.add(b"gAMA", struct.pack(">I", round(image.info["gamma"] * 100000)))
                if "srgb" in image.info:
                    text.add(b"sRGB", bytes([image.info["srgb"]]))
                if "chromaticity" in image.info:
                    text.add(
                        b"cHRM",
                        struct.pack(
                            ">8I", *(round(value * 100000) for value in image.info["chromaticity"])
                        ),
                    )
                options["pnginfo"] = text
                if "dpi" in image.info:
                    options["dpi"] = image.info["dpi"]
                if "transparency" in image.info:
                    options["transparency"] = image.info["transparency"]
            else:
                options.update(quality=95, subsampling=0)
            with os.fdopen(destination, "wb") as writer:
                rotated.save(writer, format=format, **options)
                writer.flush()
                os.fsync(writer.fileno())
        return 0
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
