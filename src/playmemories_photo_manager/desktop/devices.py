"""Read Linux device metadata for the desktop sources panel."""

import sys
from pathlib import Path

_USB_STILL_IMAGE = ("06", "01", "01")
_MAX_DEVICES = 64


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
