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
from playmemories_photo_manager.desktop.backfill_equipment import backfill_equipment
from playmemories_photo_manager.desktop.bridge import BridgeRequestError, _dispatch
from playmemories_photo_manager.gallery import GalleryQueries, GalleryQuery
from playmemories_photo_manager.gallery.calendar import capture_key, summary
from playmemories_photo_manager.gallery.errors import InvalidCursorError
from playmemories_photo_manager.imaging.service import ImageService
from playmemories_photo_manager.library import LibrarySession


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


def test_detailed_preview_adapts_to_ipc_budget_instead_of_disappearing(library):
    import random

    root, path, connection, root_id = library
    # Deterministic high-entropy input: unlike a solid-color fixture, quality=65
    # at maximum preview dimensions exceeds the existing transport limit.
    source = root / "detailed.png"
    image = Image.frombytes("RGB", (1280, 960), random.Random(42).randbytes(1280 * 960 * 3))
    old_encoding = io.BytesIO()
    image.save(old_encoding, format="JPEG", quality=65)
    assert len(old_encoding.getvalue()) > 160 * 1024
    image.save(source)
    before = source.read_bytes(), source.stat().st_mtime_ns
    apply(root, path, connection, root_id)
    asset_id = connection.execute("SELECT id FROM asset").fetchone()[0]
    service = ImageService()
    try:
        preview = wait_image(service, connection, asset_id, "preview")
        assert preview is not None
        data = base64.b64decode(preview["base64"], validate=True)
        assert len(data) <= 160 * 1024
        with Image.open(io.BytesIO(data)) as rendered:
            rendered.load()
            assert rendered.width <= 1280 and rendered.height <= 960
            assert rendered.width >= 640 and rendered.height >= 480
        assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    finally:
        close_images(service)


def test_original_dimensions_and_chunked_view_preserve_full_resolution(library):
    from playmemories_photo_manager.imaging.service import CHUNK_SIZE

    root, path, connection, root_id = library
    source = root / "large.png"
    Image.new("RGB", (4000, 4000), (25, 100, 210)).save(source)
    before = source.read_bytes()
    apply(root, path, connection, root_id)
    asset_id = connection.execute("SELECT id FROM asset").fetchone()[0]
    service = ImageService()
    try:
        assert wait_image(service, connection, asset_id, "dimensions") == {
            "width": 4000,
            "height": 4000,
        }
        first = wait_image(service, connection, asset_id, "original")
        assert first["total"] > CHUNK_SIZE
        pieces = [first]
        for offset in range(CHUNK_SIZE, first["total"], CHUNK_SIZE):
            piece = service.request(connection, asset_id, "original", offset)
            assert piece["digest"] == first["digest"]
            pieces.append(piece)
        content = b"".join(base64.b64decode(piece["base64"], validate=True) for piece in pieces)
        assert len(content) == first["total"]
        with Image.open(io.BytesIO(content)) as rendered:
            rendered.load()
            assert rendered.size == (4000, 4000)
        assert source.read_bytes() == before
    finally:
        close_images(service)


def test_gallery_filters_use_catalog_metadata_before_pagination(library):
    root, path, connection, root_id = library
    exif = Image.Exif()
    exif[272] = "ILCE-7M4"
    exif[34665] = {42036: "FE 35mm F1.8"}
    raster(root / "portrait.jpg", exif=exif)
    raster(root / "other.png", "PNG")
    apply(root, path, connection, root_id)
    queries = GalleryQueries(connection)
    portrait = queries.list_assets(GalleryQuery(media_type="image/jpeg")).items[0]
    catalog = Catalog(connection)
    catalog.set_description(portrait.asset_id, "Retrato em FLORESTÁ")
    catalog.set_rating(portrait.asset_id, 5)
    catalog.assign_tag(portrait.asset_id, "Viagens")
    tag_id = connection.execute("SELECT id FROM tag").fetchone()[0]

    page = queries.list_assets(
        GalleryQuery(
            page_size=1,
            keyword="florestá",
            tag_id=tag_id,
            rating=5,
            media_type="image/jpeg",
            camera="ILCE-7M4",
            lens="FE 35mm F1.8",
        )
    )
    assert [item.asset_id for item in page.items] == [portrait.asset_id]
    assert not page.has_more

    for facet, value in (("cameras", "ILCE-7M4"), ("lenses", "FE 35mm F1.8")):
        options = _dispatch(
            connection,
            "gallery.facets",
            {"facet": facet, "keyword": value.lower(), "offset": 0},
        )
        assert options == {"options": [{"id": value, "name": value}], "next_offset": None}

    first = queries.list_assets(GalleryQuery(page_size=1))
    assert first.next_cursor
    with pytest.raises(InvalidCursorError):
        queries.list_assets(GalleryQuery(page_size=1, after=first.next_cursor, rating=5))


def test_facet_pages_and_search_reach_labels_beyond_the_initial_options(library):
    _, _, connection, _ = library
    catalog = Catalog(connection)
    for index in range(25):
        catalog.create_tag(f"Rótulo {index:02}")
    distant = catalog.create_tag("Últimas férias")
    facets = _dispatch(connection, "gallery.list", {"include_facets": True})["facets"]
    assert len(facets["tags"]) == 24
    assert facets["more"] == ["tags"]

    def page(keyword="", offset=0):
        return _dispatch(
            connection, "gallery.facets", {"facet": "tags", "keyword": keyword, "offset": offset}
        )

    first = page()
    assert first["options"] == facets["tags"]
    assert first["next_offset"] == 24
    second = page(offset=first["next_offset"])
    assert [option["name"] for option in second["options"]] == ["Rótulo 24", "Últimas férias"]
    assert second["next_offset"] is None
    assert page(" FÉRIAS ") == {
        "options": [{"id": distant.id, "name": "Últimas férias"}],
        "next_offset": None,
    }
    assert page("ausente") == {"options": [], "next_offset": None}
    for invalid in (-1, True, 2**53):
        with pytest.raises(BridgeRequestError):
            page(offset=invalid)


def test_backfill_equipment_preserves_existing_annotations_and_skips_replaced_files(library):
    root, path, connection, root_id = library
    exif = Image.Exif()
    exif[272] = "ILCE-7M4"
    exif[34665] = {42036: "FE 35mm F1.8", 36867: "2024:02:29 23:30:00"}
    original = root / "original.jpg"
    replaced = root / "replaced.jpg"
    raster(original, exif=exif)
    raster(replaced, exif=exif)
    apply(root, path, connection, root_id)
    asset_ids = dict(
        connection.execute("SELECT normalized_relative_path, asset_id FROM file_location")
    )
    original_id = asset_ids["original.jpg"]
    capture = connection.execute(
        "SELECT captured_metadata_id FROM asset WHERE id=?", (original_id,)
    ).fetchone()[0]
    # Reproduce a catalog written before equipment observations were extracted.
    with connection:
        connection.execute("DELETE FROM metadata WHERE metadata_key IN ('Model','LensModel')")
    catalog = Catalog(connection)
    catalog.set_rating(original_id, 4)
    catalog.assign_tag(original_id, "Teste")
    before = original.read_bytes(), original.stat().st_mtime_ns
    replaced.unlink()
    replaced.symlink_to(original)
    with LibrarySession.open(path) as session:
        assert backfill_equipment(session) == {
            "verificadas": 2,
            "atualizadas": 1,
            "indisponiveis": 1,
        }
        assert backfill_equipment(session)["atualizadas"] == 0
    assert (original.read_bytes(), original.stat().st_mtime_ns) == before
    assert replaced.is_symlink()
    assert (
        connection.execute(
            "SELECT captured_metadata_id FROM asset WHERE id=?", (original_id,)
        ).fetchone()[0]
        == capture
    )
    result = GalleryQueries(connection).list_assets(
        GalleryQuery(camera="ILCE-7M4", lens="FE 35mm F1.8", rating=4, keyword="Teste")
    )
    assert [item.asset_id for item in result.items] == [original_id]
