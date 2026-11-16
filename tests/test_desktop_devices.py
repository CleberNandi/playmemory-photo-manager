import os
import sys
from uuid import uuid4

import pytest

from playmemories_photo_manager.desktop.devices import (
    list_media_devices,
    resolve_device_mount_path,
)
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


def test_resolve_device_mount_path_handles_partitions_and_escapes(tmp_path):
    sysfs = tmp_path / "sys"
    _attributes(sysfs / "block/nvme0n1", removable="0", size="100")
    _attributes(sysfs / "block/mmcblk0", removable="0", size="64")
    _attributes(sysfs / "block/mmcblk0/device", type="SD", name="Card")
    disk = sysfs / "devices/usb-storage"
    _attributes(disk, idVendor="0000", idProduct="0000")
    _attributes(disk / "sdb", removable="0", size="2048")
    (sysfs / "block/sdb").symlink_to(disk / "sdb")

    usb_mount = tmp_path / "mnt/My Camera"
    sd_mount = tmp_path / "mnt/sd"
    usb_mount.mkdir(parents=True)
    sd_mount.mkdir(parents=True)
    mounts = tmp_path / "mounts"
    mounts.write_text(
        f"/dev/nvme0n1p1 {sd_mount} ext4 rw 0 0\n"
        f"/dev/sdb1 {str(usb_mount).replace(' ', r'\040')} vfat rw 0 0\n"
        f"/dev/mmcblk0p1 {sd_mount} vfat rw 0 0\n",
        encoding="utf-8",
    )

    assert resolve_device_mount_path("storage:sdb", sysfs=sysfs, mounts_file=mounts) == usb_mount
    assert resolve_device_mount_path("storage:mmcblk0", sysfs=sysfs, mounts_file=mounts) == sd_mount
    assert resolve_device_mount_path("storage:nvme0n1", sysfs=sysfs, mounts_file=mounts) is None
    assert resolve_device_mount_path("imaging:1-2", sysfs=sysfs, mounts_file=mounts) is None
    assert resolve_device_mount_path("storage:../sdb", sysfs=sysfs, mounts_file=mounts) is None


def test_devices_import_copies_safely_preserves_mtime_and_never_overwrites(tmp_path):
    source = tmp_path / "camera_card"
    nested = source / "DCIM/100MSDCF"
    nested.mkdir(parents=True)
    photo = nested / "DSC00001.jpg"
    photo_bytes = b"\xff\xd8\xff\xe0synthetic-jpeg-1"
    photo.write_bytes(photo_bytes)
    os.utime(photo, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    (nested / "NOTES.txt").write_text("ignore", encoding="utf-8")
    (nested / "link.jpg").symlink_to(photo)

    destination = tmp_path / "library_photos"
    destination.mkdir()
    catalog_dir = tmp_path / "catalog_home"
    catalog_dir.mkdir()

    dispatcher = LibraryDispatcher()
    try:
        state = dispatcher.request(
            "library.create",
            {"path": str(catalog_dir / "test.sqlite3"), "library_handle": str(uuid4())},
        )
        session_id = state["session"]["session_id"]

        unmounted = dispatcher.request(
            "devices.import",
            {
                "session_id": session_id,
                "device_id": "imaging:1-2",
                "destination_path": str(destination),
            },
        )
        assert unmounted == {"status": "source_not_mounted"}

        first = dispatcher.request(
            "devices.import",
            {
                "session_id": session_id,
                "source_path": str(source),
                "destination_path": str(destination),
            },
        )
        assert first == {
            "status": "ready",
            "copied_count": 1,
            "skipped_count": 0,
            "excluded_count": 2,
            "destination_path": str(destination.resolve()),
        }
        copied = destination / "DCIM/100MSDCF/DSC00001.jpg"
        assert copied.read_bytes() == photo_bytes
        assert copied.stat().st_mtime_ns == 1_700_000_000_000_000_000
        assert photo.read_bytes() == photo_bytes

        # Re-importing identical file is idempotent (skipped, not duplicated)
        second = dispatcher.request(
            "devices.import",
            {
                "session_id": session_id,
                "source_path": str(source),
                "destination_path": str(destination),
            },
        )
        assert second["skipped_count"] == 1 and second["copied_count"] == 0

        # Different content at same path never overwrites; writes "DSC00001 (1).jpg"
        new_bytes = b"\xff\xd8\xff\xe0different-jpeg-2"
        photo.write_bytes(new_bytes)
        third = dispatcher.request(
            "devices.import",
            {
                "session_id": session_id,
                "source_path": str(source),
                "destination_path": str(destination),
            },
        )
        assert third["copied_count"] == 1
        assert copied.read_bytes() == photo_bytes
        assert (destination / "DCIM/100MSDCF/DSC00001 (1).jpg").read_bytes() == new_bytes

        # Rejects unsafe destinations (catalog dir, same dir, nested dir)
        for bad_dest in (catalog_dir, source, nested):
            with pytest.raises(LibraryError, match="unsafe_location"):
                dispatcher.request(
                    "devices.import",
                    {
                        "session_id": session_id,
                        "source_path": str(source),
                        "destination_path": str(bad_dest),
                    },
                )
    finally:
        dispatcher.close()
