"""Explicit full-resolution edits use synthetic media and reconcile logical identity."""

import time
from uuid import uuid4

import pytest
from PIL import Image
from test_desktop_media_location import source as _source_fixture

from playmemories_photo_manager.catalog import connect
from playmemories_photo_manager.library import LibraryError

source = _source_fixture


def save(fixture, mode="replace", target=None, angle=90):
    dispatcher, _, session, _, _, asset = fixture
    result = dispatcher.request(
        "image.save",
        {
            "session_id": session,
            "asset_id": asset,
            "angle": angle,
            "mode": mode,
            "target": str(target) if target else None,
            "request_id": str(uuid4()),
        },
    )
    for _ in range(400):
        dispatcher.tick()
        result = dispatcher.request(
            "image.save_status", {"session_id": session, "job_id": result["job_id"]}
        )
        if result["state"] != "running":
            return result
        time.sleep(0.02)
    raise AssertionError("rotation timed out")


def test_replace_keeps_asset_and_updates_observation(source):
    dispatcher, path, session, root, image, asset = source
    result = save(source)
    assert result["state"] == "completed", result
    assert result["result_asset_id"] == asset
    with Image.open(image) as rotated:
        assert rotated.size == (40, 80)
    assert dispatcher.request("asset.reveal", {"session_id": session, "asset_id": asset})[
        "path"
    ] == str(image)
    with connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM asset").fetchone()[0] == 1
    assert not list(root.glob(".playmemories-*"))


def test_copy_preserves_source_and_registers_new_asset(source):
    dispatcher, _, session, root, image, asset = source
    before = image.read_bytes()
    target = root / "copy.jpg"
    result = save(source, "copy", target)
    assert result["state"] == "completed", result
    assert image.read_bytes() == before
    assert result["result_asset_id"] != asset
    with Image.open(target) as rotated:
        assert rotated.size == (40, 80)
    page = dispatcher.request("gallery.list", {"session_id": session})
    assert len(page["items"]) == 2
    assert not list(root.glob(".playmemories-*"))


def test_copy_does_not_overwrite_existing_file(source):
    *_, root, image, _ = source
    target = root / "existing.jpg"
    target.write_bytes(b"keep")
    with pytest.raises(LibraryError):
        save(source, "copy", target)
    assert target.read_bytes() == b"keep"
    with pytest.raises(LibraryError):
        save(source, "copy", root.parent / "outside.jpg")
    assert image.exists()


def test_replace_rejects_hardlinks_and_invalid_angles(source):
    *_, root, image, _ = source
    import os

    os.link(image, root / "hardlink.jpg")
    with pytest.raises(LibraryError):
        save(source)
    with pytest.raises(LibraryError):
        save(source, angle=True)


def test_png_copy_rotates_pixels_alpha_and_preserves_embedded_date_and_text(tmp_path):
    from PIL import PngImagePlugin
    from test_real_images_calendar import apply

    from playmemories_photo_manager.catalog import Catalog
    from playmemories_photo_manager.desktop.libraries import LibraryDispatcher

    dispatcher = LibraryDispatcher()
    path = tmp_path / "catalog.sqlite3"
    session = dispatcher.request(
        "library.create", {"path": str(path), "library_handle": str(uuid4())}
    )["session"]["session_id"]
    root = tmp_path / "media"
    root.mkdir()
    image = root / "source.png"
    pixels = Image.new("RGBA", (1600, 1000))
    pixels.putdata(
        [
            (255, 0, 0, 100),
            (0, 255, 0, 120),
            (0, 0, 255, 140),
            (10, 20, 30, 160),
            (40, 50, 60, 180),
            (70, 80, 90, 200),
        ]
    )
    exif = Image.Exif()
    exif[36867] = "2024:02:29 10:20:30"
    text = PngImagePlugin.PngInfo()
    text.add_text("Creation Time", "2024-02-29T10:20:30")
    pixels.save(image, exif=exif, pnginfo=text)
    with connect(path) as connection:
        root_id = Catalog(connection).register_root("Synthetic", str(root)).id
        apply(root, path, connection, root_id)
        asset = connection.execute("SELECT id FROM asset").fetchone()[0]
    fixture = dispatcher, path, session, root, image, asset
    try:
        before = image.read_bytes()
        result = save(fixture, "copy", root / "copy.png")
        assert result["state"] == "completed", result
        with Image.open(root / "copy.png") as rotated:
            assert rotated.size == (1000, 1600)
            assert rotated.tobytes() == pixels.transpose(Image.Transpose.ROTATE_270).tobytes()
            assert rotated.text["Creation Time"] == "2024-02-29T10:20:30"
            assert rotated.getexif()[36867] == exif[36867]
        assert image.read_bytes() == before
        details = dispatcher.request(
            "asset.details", {"session_id": session, "asset_id": result["result_asset_id"]}
        )
        assert details["capture"]["local_value"] == "2024-02-29T10:20:30"
    finally:
        dispatcher.close()


def test_rolls_back_physical_replace_when_catalog_update_fails(source, monkeypatch):
    import sqlite3
    from contextlib import contextmanager

    dispatcher, _, _, root, image, _ = source
    before = image.read_bytes()
    active = dispatcher.owner.active
    original = active.command_connection

    class FaultyConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, *args):
            if sql.startswith("UPDATE asset SET byte_size"):
                raise sqlite3.OperationalError("injected failure")
            return self.connection.execute(sql, *args)

        def commit(self):
            return self.connection.commit()

    @contextmanager
    def faulty():
        with original() as connection:
            yield FaultyConnection(connection)

    monkeypatch.setattr(active, "command_connection", faulty)
    result = save(source)
    assert result["state"] == "failed", result
    assert image.read_bytes() == before
    assert not list(root.glob(".playmemories-*"))


def test_source_change_during_encoding_blocks_publication(source):
    dispatcher, _, session, root, image, asset = source
    job = dispatcher.request(
        "image.save",
        {
            "session_id": session,
            "asset_id": asset,
            "angle": 90,
            "mode": "replace",
            "target": None,
            "request_id": str(uuid4()),
        },
    )
    image.write_bytes(b"external modification")
    for _ in range(400):
        dispatcher.tick()
        result = dispatcher.request(
            "image.save_status", {"session_id": session, "job_id": job["job_id"]}
        )
        if result["state"] != "running":
            break
        time.sleep(0.02)
    assert result["state"] == "failed", result
    assert image.read_bytes() == b"external modification"
    assert not list(root.glob(".playmemories-*"))


def test_lost_commit_ack_keeps_recovery_backup_and_never_retries(source, monkeypatch):
    import sqlite3
    from contextlib import contextmanager

    dispatcher, _, _, root, image, _ = source
    before = image.read_bytes()
    active = dispatcher.owner.active
    original = active.command_connection

    class UncertainConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, *args):
            return self.connection.execute(*args)

        def commit(self):
            self.connection.commit()
            raise sqlite3.OperationalError("lost acknowledgement")

    @contextmanager
    def uncertain():
        with original() as connection:
            yield UncertainConnection(connection)

    monkeypatch.setattr(active, "command_connection", uncertain)
    result = save(source)
    assert result["state"] == "outcome_unknown", result
    backups = list(root.glob(".playmemories-before-*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before
    with pytest.raises(LibraryError):
        save(source)
    assert not list(root.glob(".playmemories-edit-*.tmp"))


def test_replace_refuses_extended_acl_instead_of_broadening_access(source, monkeypatch):
    import os

    before = source[4].read_bytes()
    monkeypatch.setattr(os, "listxattr", lambda fd: ["system.posix_acl_access"])
    with pytest.raises(LibraryError):
        save(source)
    assert source[4].read_bytes() == before
    assert not list(source[3].glob(".playmemories-*"))
