import sys
from uuid import uuid4

import pytest

from playmemories_photo_manager.desktop.devices import list_media_devices
from playmemories_photo_manager.desktop.libraries import LibraryDispatcher
from playmemories_photo_manager.library import LibraryError

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux sysfs")


def _attributes(directory, **values):
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in values.items():
        (directory / name).write_text(value, encoding="utf-8")


def test_media_discovery_deduplicates_interfaces_and_excludes_internal_and_empty_drives(tmp_path):
    usb = tmp_path / "bus/usb/devices"
    _attributes(usb / "1-2", product="Synthetic Camera\n", serial="must-not-be-exposed")
    for name in ("1-2:1.0", "1-2:1.1"):
        _attributes(
            usb / name, bInterfaceClass="06", bInterfaceSubClass="01", bInterfaceProtocol="01"
        )
    _attributes(usb / "1-3:1.0", bInterfaceClass="0e")
    _attributes(tmp_path / "block/nvme0n1", removable="0", size="100")
    _attributes(tmp_path / "block/sr0", removable="1", size="0")
    _attributes(tmp_path / "block/mmcblk0", removable="0", size="64")
    _attributes(tmp_path / "block/mmcblk0/device", type="SD", name="Synthetic Card")
    disk = tmp_path / "devices/usb-storage"
    _attributes(disk, idVendor="0000", idProduct="0000")
    _attributes(disk / "sdb", removable="0", size="2048")
    _attributes(disk / "sdb/device", model="Synthetic USB disk")
    (tmp_path / "block/sdb").symlink_to(disk / "sdb")
    (tmp_path / "block/sdc").symlink_to(disk / "gone")

    result = list_media_devices(tmp_path)
    assert result == {
        "status": "ready",
        "devices": [
            {"id": "imaging:1-2", "name": "Synthetic Camera", "kind": "imaging"},
            {"id": "storage:mmcblk0", "name": "Synthetic Card", "kind": "storage"},
            {"id": "storage:sdb", "name": "Synthetic USB disk", "kind": "storage"},
        ],
        "total_count": 3,
    }
    (usb / "1-2:1.0/bInterfaceClass").unlink()
    (usb / "1-2:1.1/bInterfaceClass").unlink()
    assert list_media_devices(tmp_path)["total_count"] == 2


def test_device_inventory_rejects_path_and_requires_active_library(tmp_path, monkeypatch):
    import playmemories_photo_manager.desktop.devices as devices

    result = {"status": "ready", "devices": [], "total_count": 0}
    monkeypatch.setattr(devices, "list_media_devices", lambda: result)
    dispatcher = LibraryDispatcher()
    try:
        state = dispatcher.request(
            "library.create",
            {"path": str(tmp_path / "test.sqlite3"), "library_handle": str(uuid4())},
        )
        session_id = state["session"]["session_id"]
        assert dispatcher.request("devices.list", {"session_id": session_id}) == result
        with pytest.raises(LibraryError, match="invalid_request"):
            dispatcher.request("devices.list", {"session_id": session_id, "path": str(tmp_path)})
        with pytest.raises(LibraryError, match="stale_session"):
            dispatcher.request("devices.list", {"session_id": str(uuid4())})
    finally:
        dispatcher.close()
