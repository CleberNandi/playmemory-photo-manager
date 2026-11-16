"""Read Linux device metadata for the desktop sources panel."""

import re
import sys
from pathlib import Path

_USB_STILL_IMAGE = ("06", "01", "01")
_MAX_DEVICES = 64
_OCTAL_ESCAPE = re.compile(r"\\([0-7]{3})")


def _attribute(directory: Path, name: str) -> str:
    try:
        with (directory / name).open(encoding="utf-8", errors="replace") as attribute:
            value = attribute.read(256)
    except OSError:
        return ""
    return "".join(char for char in value.strip() if char.isprintable())


def _cameras(entries: list[Path]):
    seen: set[str] = set()
    for interface in entries:
        device_name, separator, _ = interface.name.partition(":")
        if not separator or device_name in seen:
            continue
        descriptor = tuple(
            _attribute(interface, field)
            for field in ("bInterfaceClass", "bInterfaceSubClass", "bInterfaceProtocol")
        )
        if descriptor != _USB_STILL_IMAGE:
            continue
        device = interface.with_name(device_name)
        seen.add(device_name)
        yield {
            "id": f"imaging:{device_name}",
            "name": _attribute(device, "product") or "Dispositivo de imagem USB",
            "kind": "imaging",
        }


def _storage(entries: list[Path], sysfs: Path):
    for block in entries:
        try:
            physical = block.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        removable = _attribute(block, "removable") == "1"
        card = _attribute(block, "device/type") in {"SD", "SDcombo"}
        usb = any(
            _attribute(parent, "idVendor") and _attribute(parent, "idProduct")
            for parent in physical.parents
            if parent.is_relative_to(sysfs)
        )
        if not (removable or card or usb):
            continue
        size = _attribute(block, "size")
        if not size.isascii() or not size.isdigit() or int(size) == 0:
            continue
        yield {
            "id": f"storage:{block.name}",
            "name": _attribute(block, "device/model")
            or _attribute(block, "device/name")
            or block.name,
            "kind": "storage",
        }


def list_media_devices(sysfs: Path = Path("/sys")) -> dict:
    if sys.platform != "linux":
        return {"status": "unsupported"}
    try:
        usb = sorted((sysfs / "bus/usb/devices").iterdir())
        block = sorted((sysfs / "block").iterdir())
    except OSError:
        return {"status": "unavailable"}
    devices = [*_cameras(usb), *_storage(block, sysfs)]
    return {"status": "ready", "devices": devices[:_MAX_DEVICES], "total_count": len(devices)}


def _unescape_mount_path(raw: str) -> str:
    return _OCTAL_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), raw)


def resolve_device_mount_path(
    device_id: str,
    *,
    sysfs: Path = Path("/sys"),
    mounts_file: Path = Path("/proc/self/mounts"),
) -> Path | None:
    """Resolve the mounted directory for a removable/USB storage device_id on Linux."""
    if sys.platform != "linux" or not isinstance(device_id, str):
        return None
    kind, sep, block_name = device_id.partition(":")
    if kind != "storage" or not sep or not block_name:
        return None
    if block_name in {".", ".."} or "/" in block_name or "\\" in block_name or "\0" in block_name:
        return None
    block_dir = sysfs / "block" / block_name
    if not any(item["id"] == device_id for item in _storage([block_dir], sysfs)):
        return None
    try:
        lines = mounts_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    dev_prefix = f"/dev/{block_name}"
    for line in lines:
        parts = line.split(" ")
        if len(parts) < 2:
            continue
        source_dev, target_raw = parts[0], parts[1]
        if source_dev != dev_prefix:
            if not source_dev.startswith(dev_prefix):
                continue
            suffix = source_dev[len(dev_prefix) :]
            if not (suffix.isdigit() or (suffix.startswith("p") and suffix[1:].isdigit())):
                continue
        candidate = Path(_unescape_mount_path(target_raw))
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_dir():
            return resolved
    return None
