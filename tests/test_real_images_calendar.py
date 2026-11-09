"""Synthetic formats, temporal provenance, confined rendering and calendar."""

import base64
import io
import os
import time

import pytest
from PIL import Image
from test_scoped_application import prepare

from playmemories_photo_manager.catalog import Catalog, initialize_database
from playmemories_photo_manager.catalog_ingestion import (
    apply_scoped_ingestion,
    authorize_scoped_ingestion,
)
from playmemories_photo_manager.catalog_ingestion.media import _mount_id
from playmemories_photo_manager.desktop.bridge import BridgeRequestError, _dispatch
from playmemories_photo_manager.gallery import GalleryQueries, GalleryQuery
from playmemories_photo_manager.gallery.calendar import capture_key, summary
from playmemories_photo_manager.gallery.errors import InvalidCursorError
from playmemories_photo_manager.imaging.service import ImageService


def raster(path, format="JPEG", **options):
    image = Image.new("RGB", (80, 40), (25, 100, 210))
    image.save(path, format=format, **options)


def apply(root, path, connection, root_id):
    scoped = prepare(root, path, root_id)
    ids = tuple(
        item.candidate_id
        for item in scoped.eligibilities
        if item.candidate in scoped.eligible_candidates
    )
    auth = authorize_scoped_ingestion(scoped, ids)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        report = apply_scoped_ingestion(
            Catalog(connection), scoped, auth, expected_root_mount=_mount_id(fd)
        )
    finally:
        os.close(fd)
    assert report.status.value == "applied", report
    return scoped


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    path = tmp_path / "catalog.sqlite3"
    connection = initialize_database(path)
    root_id = Catalog(connection).register_root("Synthetic", str(root)).id
    yield root, path, connection, root_id
    connection.close()


@pytest.mark.parametrize(
    "format,extension,options",
    [
        ("JPEG", "jpg", {}),
        ("JPEG", "jpeg", {"progressive": True}),
        ("PNG", "png", {}),
        ("WEBP", "webp", {}),
        ("GIF", "gif", {}),
        ("BMP", "bmp", {}),
        ("TIFF", "tiff", {}),
        ("ICO", "ico", {}),
        ("AVIF", "avif", {}),
    ],
)
def test_formats_apply_and_render_without_original_changes(library, format, extension, options):
    root, path, connection, root_id = library
    source = root / f"sample.{extension}"
    raster(source, format, **options)
    before = source.read_bytes(), source.stat().st_mtime_ns
    scoped = apply(root, path, connection, root_id)
    assert len(scoped.eligible_candidates) == 1
    asset_id = connection.execute("SELECT id FROM asset").fetchone()[0]
    renderer = ImageService()
    try:
        for variant in ("grid", "preview"):
            value = wait_image(renderer, connection, asset_id, variant)
            assert value and value["synthetic"] is False
            with Image.open(io.BytesIO(base64.b64decode(value["base64"]))) as image:
                assert image.size == (256, 160) if variant == "grid" else image.width <= 1280
        assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    finally:
        close_images(renderer)


def wait_image(service, connection, asset_id, variant="grid"):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = service.request(connection, asset_id, variant)
        if result is None or result.get("status") != "pending":
            return result
        time.sleep(0.01)
    pytest.fail("image worker did not terminate")


def close_images(service):
    deadline = time.monotonic() + 2
    while not service.shutdown():
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_exif_provenance_and_calendar_across_pages(library):
    root, path, connection, root_id = library
    exif = Image.Exif()
    exif[34665] = {36867: "2024:02:29 23:30:00", 36881: "-03:00", 36868: "2024:03:01 02:30:00"}
    raster(root / "capture.jpg", exif=exif, progressive=True)
    raster(root / "undated.png", "PNG")
    apply(root, path, connection, root_id)
    rows = connection.execute("SELECT * FROM asset ORDER BY media_type").fetchall()
    captured = next(row for row in rows if row["captured_local_value"])
    assert captured["captured_local_value"] == "2024-02-29T23:30:00"
    assert captured["captured_offset_minutes"] == -180
    assert captured["captured_source_kind"] == "metadata"
    assert (
        connection.execute(
            "SELECT raw_value FROM metadata WHERE id=?", (captured["captured_metadata_id"],)
        ).fetchone()[0]
        == "2024:02:29 23:30:00"
    )
    assert summary(connection)["buckets"] == [["2024", 1]]
    assert summary(connection, "2024-02")["buckets"] == [["2024-02-29", 1]]
    assert summary(connection)["undated"] == 1
    queries = GalleryQueries(connection)
    assert (
        queries.list_assets(GalleryQuery(capture_period="2024-02-29")).items[0].asset_id
        == captured["id"]
    )
    assert len(queries.list_assets(GalleryQuery(capture_period="undated")).items) == 1
    all_page = queries.list_assets(GalleryQuery(page_size=1))
    assert all_page.next_cursor
    with pytest.raises(InvalidCursorError):
        queries.list_assets(
            GalleryQuery(page_size=1, after=all_page.next_cursor, capture_period="2024")
        )
    # Pure calendar reads never create temporal observations or convert local days to UTC.
    assert summary(connection, "2024-03")["buckets"] == []


def test_invalid_capture_preserved_without_import_date_fallback(library):
    root, path, connection, root_id = library
    exif = Image.Exif()
    exif[34665] = {36867: "2024:02:30 00:00:00", 36881: "+99:99"}
    raster(root / "invalid.jpg", exif=exif)
    apply(root, path, connection, root_id)
    assert connection.execute("SELECT captured_local_value FROM asset").fetchone()[0] is None
    row = connection.execute(
        "SELECT raw_value,parse_error FROM metadata WHERE metadata_key='DateTimeOriginal'"
    ).fetchone()
    assert tuple(row) == ("2024:02:30 00:00:00", "invalid_capture_value")
    assert summary(connection)["undated"] == 1


@pytest.mark.parametrize("alter", ["symlink", "replace", "modify", "offline"])
def test_render_rejects_changed_or_unavailable_occurrence(library, alter):
    root, path, connection, root_id = library
    source = root / "sample.png"
    raster(source, "PNG")
    apply(root, path, connection, root_id)
    asset_id = connection.execute("SELECT id FROM asset").fetchone()[0]
    service = ImageService()
    try:
        assert wait_image(service, connection, asset_id)
        if alter == "symlink":
            target = root / "other.png"
            source.rename(target)
            source.symlink_to(target)
        elif alter == "replace":
            source.unlink()
            raster(source, "PNG")
        elif alter == "modify":
            source.write_bytes(b"changed")
        else:
            connection.execute("UPDATE library_root SET availability='offline'")
        assert service.request(connection, asset_id, "grid") is None
    finally:
        close_images(service)


def test_partial_capture_does_not_gain_day_precision(library):
    _, _, connection, _ = library
    identifier = Catalog(connection).create_asset("photo").id
    connection.execute(
        "UPDATE asset SET captured_local_value='2024-02',captured_precision='month',"
        "captured_source_kind='manual',captured_timezone_state='unknown' WHERE id=?",
        (identifier,),
    )
    assert summary(connection, "2024")["buckets"] == [["2024-02", 1]]
    assert summary(connection, "2024-02")["partial"] == 1
    assert summary(connection, "2024-02")["buckets"] == []
    assert capture_key("2024-02-30T00:00:00", "second") is None
    for period in ("../../private", "2024-13", "2023-02-29", True):
        with pytest.raises((BridgeRequestError, ValueError)):
            _dispatch(connection, "calendar.summary", {"period": period})


def test_calendar_counts_whole_catalog_and_filtered_pagination(library):
    _, _, connection, _ = library
    catalog = Catalog(connection)
    for index in range(55):
        asset = catalog.create_asset("photo")
        value = "2024-02-29T12:00:00" if index < 50 else None
        if value:
            connection.execute(
                "UPDATE asset SET captured_local_value=?,captured_precision='second',"
                "captured_source_kind='manual',captured_timezone_state='unknown' WHERE id=?",
                (value, asset.id),
            )
    queries = GalleryQueries(connection)
    assert len(queries.list_assets(GalleryQuery(page_size=24)).items) == 24
    assert summary(connection)["buckets"] == [["2024", 50]]
    assert summary(connection, "2024-02")["buckets"] == [["2024-02-29", 50]]
    seen = set()
    after = None
    while True:
        page = queries.list_assets(
            GalleryQuery(page_size=24, after=after, capture_period="2024-02")
        )
        for item in page.items:
            assert item.asset_id not in seen
            seen.add(item.asset_id)
        if not page.has_more:
            break
        after = page.next_cursor
    assert len(seen) == 50
    assert summary(connection)["undated"] == 5


def test_metadata_failure_rolls_back_assets_locations_and_observations(library, monkeypatch):
    from playmemories_photo_manager.catalog_ingestion import scoped_application

    root, path, connection, root_id = library
    exif = Image.Exif()
    exif[34665] = {36867: "2024:02:29 12:00:00"}
    raster(root / "sample.jpg", exif=exif)
    original = scoped_application.persist_capture

    def fail_after_metadata(*args):
        original(*args)
        raise RuntimeError("synthetic metadata failure")

    monkeypatch.setattr(scoped_application, "persist_capture", fail_after_metadata)
    with pytest.raises(RuntimeError, match="synthetic metadata failure"):
        apply(root, path, connection, root_id)
    for table in ("asset", "file_location", "metadata"):
        assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_worker_timeout_reaps_and_releases_all_descriptors(library, monkeypatch):
    from playmemories_photo_manager.imaging import service as module

    root, path, connection, root_id = library
    raster(root / "sample.png", "PNG")
    apply(root, path, connection, root_id)
    asset_id = connection.execute("SELECT id FROM asset").fetchone()[0]
    spawn = module.subprocess.Popen

    def hang(_command, **options):
        return spawn([module.sys.executable, "-c", "import time;time.sleep(60)"], **options)

    monkeypatch.setattr(module.subprocess, "Popen", hang)
    service = ImageService()
    assert service.request(connection, asset_id, "grid") == {"status": "pending"}
    key, job = next(iter(service.jobs.items()))
    process, _, data, directories, fd, parent, name, state = job
    service.jobs[key] = (process, time.monotonic() - 1, data, directories, fd, parent, name, state)
    try:
        assert wait_image(service, connection, asset_id) is None
        assert process.poll() is not None
        assert not service.jobs
        with pytest.raises(OSError):
            os.fstat(fd)
    finally:
        close_images(service)


def test_changed_parent_symlink_and_mutation_during_render_fail_closed(library):
    root, path, connection, root_id = library
    nested = root / "nested"
    nested.mkdir()
    source = nested / "image.png"
    raster(source, "PNG")
    apply(root, path, connection, root_id)
    asset_id = connection.execute("SELECT id FROM asset").fetchone()[0]
    service = ImageService()
    try:
        assert service.request(connection, asset_id, "grid") == {"status": "pending"}
        target = root / "moved"
        nested.rename(target)
        nested.symlink_to(target, target_is_directory=True)
        assert wait_image(service, connection, asset_id) is None
        deadline = time.monotonic() + 8
        while service.jobs:
            assert time.monotonic() < deadline
            service.tick()
            time.sleep(0.01)
        assert all(value is None for value in service.cache.values())
    finally:
        close_images(service)
