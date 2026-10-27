from __future__ import annotations

import dataclasses
import os
import sqlite3
import uuid
from pathlib import Path

import pytest

from playmemories_photo_manager.gallery import (
    AssetAvailability,
    AssetNotFoundError,
    GalleryQueries,
    GalleryQuery,
    InvalidCursorError,
    InvalidGalleryQueryError,
    InvalidThumbnailError,
    MetadataState,
    SyntheticThumbnailFixture,
    SyntheticThumbnailStore,
    ThumbnailNotFoundError,
    ThumbnailTooLargeError,
    ThumbnailVariant,
    UnsafeThumbnailPathError,
)


def _id(number: int) -> str:
    return str(uuid.UUID(int=number))


def _asset(
    database: sqlite3.Connection,
    number: int,
    *,
    created_at: str = "2026-01-01T00:00:00.000Z",
    kind: str = "photo",
    sha256: str | None = None,
) -> str:
    identifier = _id(number)
    hash_state = "verified" if sha256 else "absent"
    database.execute(
        """INSERT INTO asset(id, kind, sha256, hash_state, byte_size, media_type, created_at)
        VALUES (?, ?, ?, ?, 12, 'image/jpeg', ?)""",
        (identifier, kind, sha256, hash_state, created_at),
    )
    return identifier


def _root(
    database: sqlite3.Connection,
    number: int,
    *,
    availability: str = "available",
) -> str:
    identifier = _id(number)
    database.execute(
        """INSERT INTO library_root(id, display_name, normalized_path, availability)
        VALUES (?, ?, ?, ?)""",
        (identifier, f"Root {number}", f"/private/library-{number}", availability),
    )
    return identifier


def _location(
    database: sqlite3.Connection,
    number: int,
    asset_id: str,
    root_id: str,
    *,
    relative_path: str | None = None,
    availability: str = "present",
    entry_type: str = "file",
) -> str:
    identifier = _id(number)
    database.execute(
        """INSERT INTO file_location(
            id, asset_id, library_root_id, normalized_relative_path, entry_type, symlink_target,
            availability,
            observed_byte_size, observed_mtime_ns, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 12, 42, '2026-01-02T00:00:00Z')""",
        (
            identifier,
            asset_id,
            root_id,
            relative_path or f"folder/{number}.jpg",
            entry_type,
            "target.jpg" if entry_type == "symlink" else None,
            availability,
        ),
    )
    return identifier


def test_empty_catalog(database: sqlite3.Connection) -> None:
    page = GalleryQueries(database).list_assets()

    assert page.items == ()
    assert page.next_cursor is None
    assert page.has_more is False


def test_keyset_first_and_next_pages_are_stable(database: sqlite3.Connection) -> None:
    expected = [_asset(database, number) for number in range(1, 6)]
    queries = GalleryQueries(database)

    first = queries.list_assets(GalleryQuery(page_size=2))
    second = queries.list_assets(GalleryQuery(page_size=2, after=first.next_cursor))
    third = queries.list_assets(GalleryQuery(page_size=2, after=second.next_cursor))

    assert [item.asset_id for page in (first, second, third) for item in page.items] == expected
    assert first.has_more and second.has_more
    assert third.has_more is False
    assert third.next_cursor is None


def test_tied_timestamps_are_ordered_by_asset_uuid(database: sqlite3.Connection) -> None:
    inserted = [_asset(database, number) for number in (30, 10, 20)]

    page = GalleryQueries(database).list_assets(GalleryQuery(page_size=100))

    assert [item.asset_id for item in page.items] == sorted(inserted)


def test_invalid_and_modified_cursor_are_rejected(database: sqlite3.Connection) -> None:
    _asset(database, 1)
    _asset(database, 2)
    queries = GalleryQueries(database)
    cursor = queries.list_assets(GalleryQuery(page_size=1)).next_cursor
    assert cursor is not None

    with pytest.raises(InvalidCursorError):
        queries.list_assets(GalleryQuery(after="not-base64!"))
    changed = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
    with pytest.raises(InvalidCursorError):
        queries.list_assets(GalleryQuery(after=changed))


def test_cursor_is_bound_to_filters(database: sqlite3.Connection) -> None:
    _asset(database, 1)
    _asset(database, 2)
    queries = GalleryQueries(database)
    cursor = queries.list_assets(GalleryQuery(page_size=1, kind="photo")).next_cursor

    with pytest.raises(InvalidCursorError):
        queries.list_assets(GalleryQuery(page_size=1, after=cursor, kind="video"))


@pytest.mark.parametrize("page_size", [0, 101, True])
def test_page_size_is_strictly_validated(database: sqlite3.Connection, page_size: object) -> None:
    with pytest.raises(InvalidGalleryQueryError):
        GalleryQueries(database).list_assets(GalleryQuery(page_size=page_size))  # type: ignore[arg-type]


def test_filters_use_membership_without_hiding_detail_locations(
    database: sqlite3.Connection,
) -> None:
    asset_id = _asset(database, 1)
    matching_root = _root(database, 101)
    other_root = _root(database, 102, availability="offline")
    _location(database, 201, asset_id, matching_root)
    _location(database, 202, asset_id, other_root, availability="offline")
    queries = GalleryQueries(database)

    page = queries.list_assets(
        GalleryQuery(root_id=matching_root, availability=AssetAvailability.AVAILABLE)
    )
    details = queries.get_asset_details(asset_id)

    assert [item.asset_id for item in page.items] == [asset_id]
    assert len(details.locations) == 2
    assert page.items[0].representative_location.id == _id(201)


def test_offline_and_missing_are_persisted_projections(database: sqlite3.Connection) -> None:
    offline_asset = _asset(database, 1)
    missing_asset = _asset(database, 2)
    offline_root = _root(database, 101, availability="offline")
    online_root = _root(database, 102)
    _location(database, 201, offline_asset, offline_root, availability="offline")
    _location(database, 202, missing_asset, online_root, availability="missing")
    queries = GalleryQueries(database)

    page = queries.list_assets()

    assert {item.asset_id: item.availability for item in page.items} == {
        offline_asset: AssetAvailability.OFFLINE,
        missing_asset: AssetAvailability.UNAVAILABLE,
    }


def test_distinct_assets_with_same_hash_are_not_merged(database: sqlite3.Connection) -> None:
    digest = "a" * 64
    first = _asset(database, 1, sha256=digest)
    second = _asset(database, 2, sha256=digest)

    page = GalleryQueries(database).list_assets()

    assert [item.asset_id for item in page.items] == [first, second]


def test_details_expose_annotations_tags_metadata_and_capture_provenance(
    database: sqlite3.Connection,
) -> None:
    asset_id = _asset(database, 1)
    metadata_id = _id(301)
    tag_id = _id(401)
    database.execute(
        """INSERT INTO metadata(
            id, asset_id, namespace, metadata_key, source, source_key, raw_value,
            interpreted_value, value_type, temporal_local_value, temporal_precision,
            timezone_state, extractor_version, extracted_at
        ) VALUES (?, ?, 'exif', 'DateTimeOriginal', 'embedded', '0x9003',
            '2020:01:02 03:04:05', '2020-01-02T03:04:05', 'datetime',
            '2020-01-02T03:04:05', 'second', 'unknown', 'fixture-1',
            '2026-01-01T00:00:00Z')""",
        (metadata_id, asset_id),
    )
    database.execute(
        """UPDATE asset SET captured_local_value = '2020-01-02T03:04:05',
            captured_timezone_state = 'unknown', captured_precision = 'second',
            captured_source_kind = 'metadata', captured_metadata_id = ?,
            captured_selection_reason = 'exif_datetime_original' WHERE id = ?""",
        (metadata_id, asset_id),
    )
    database.execute(
        """INSERT INTO user_annotation(asset_id, rating, favorite, title, description)
        VALUES (?, 5, 1, 'Chosen', 'Synthetic')""",
        (asset_id,),
    )
    database.execute(
        "INSERT INTO tag(id, display_name, normalized_key) VALUES (?, 'Trip', 'trip')", (tag_id,)
    )
    database.execute("INSERT INTO asset_tag(asset_id, tag_id) VALUES (?, ?)", (asset_id, tag_id))

    details = GalleryQueries(database).get_asset_details(asset_id)

    assert details.metadata_state is MetadataState.EXTRACTED
    assert details.metadata[0].raw_value == "2020:01:02 03:04:05"
    assert details.capture.metadata_id == metadata_id
    assert details.capture.timezone_state.value == "unknown"
    assert details.annotation.favorite is True
    assert details.tags[0].display_name == "Trip"


def test_empty_metadata_means_not_extracted_and_does_not_invent_capture(
    database: sqlite3.Connection,
) -> None:
    asset_id = _asset(database, 1)

    details = GalleryQueries(database).get_asset_details(asset_id)

    assert details.metadata_state is MetadataState.NOT_EXTRACTED
    assert details.metadata == ()
    assert details.capture is None


def test_capture_without_timezone_remains_floating_local_time(
    database: sqlite3.Connection,
) -> None:
    asset_id = _asset(database, 1)
    database.execute(
        """UPDATE asset SET captured_local_value = '2020-01-02T03:04:05',
            captured_timezone_state = NULL, captured_precision = 'second',
            captured_source_kind = 'manual', captured_selection_reason = 'user_supplied'
            WHERE id = ?""",
        (asset_id,),
    )

    details = GalleryQueries(database).get_asset_details(asset_id)

    assert details.capture is not None
    assert details.capture.local_value == "2020-01-02T03:04:05"
    assert details.capture.timezone_state is None
    assert details.capture.offset_minutes is None
    assert details.capture.timezone_name is None


def test_present_symlink_is_not_an_available_asset(database: sqlite3.Connection) -> None:
    asset_id = _asset(database, 1)
    root_id = _root(database, 101)
    location_id = _location(database, 201, asset_id, root_id, entry_type="symlink")
    queries = GalleryQueries(database)

    item = queries.list_assets().items[0]
    details = queries.get_asset_details(asset_id)

    assert item.availability is AssetAvailability.UNAVAILABLE
    assert details.availability is AssetAvailability.UNAVAILABLE
    assert item.representative_location.id == location_id


def test_regular_file_wins_over_symlink_and_keeps_asset_available(
    database: sqlite3.Connection,
) -> None:
    asset_id = _asset(database, 1)
    root_id = _root(database, 101)
    _location(database, 201, asset_id, root_id, entry_type="symlink")
    regular_id = _location(database, 202, asset_id, root_id)
    queries = GalleryQueries(database)

    item = queries.list_assets().items[0]
    details = queries.get_asset_details(asset_id)

    assert item.availability is AssetAvailability.AVAILABLE
    assert details.availability is AssetAvailability.AVAILABLE
    assert item.representative_location.id == regular_id


def test_unknown_asset_details(database: sqlite3.Connection) -> None:
    with pytest.raises(AssetNotFoundError, match="asset not found"):
        GalleryQueries(database).get_asset_details(_id(999))


def test_details_signal_location_truncation_without_losing_aggregate_state(
    database: sqlite3.Connection,
) -> None:
    asset_id = _asset(database, 1)
    root_id = _root(database, 1000)
    for number in range(2000, 2101):
        _location(database, number, asset_id, root_id, availability="missing")
    database.execute("UPDATE file_location SET availability = 'present' WHERE id = ?", (_id(2100),))

    details = GalleryQueries(database).get_asset_details(asset_id)

    assert len(details.locations) == 100
    assert details.locations_truncated is True
    assert details.availability is AssetAvailability.AVAILABLE


def test_ui_dtos_do_not_expose_absolute_library_paths(database: sqlite3.Connection) -> None:
    asset_id = _asset(database, 1)
    root_id = _root(database, 101)
    _location(database, 201, asset_id, root_id)

    page = GalleryQueries(database).list_assets()
    details = GalleryQueries(database).get_asset_details(asset_id)
    serialized = repr((dataclasses.asdict(page.items[0]), dataclasses.asdict(details)))

    assert "/private/library" not in serialized
    assert "normalized_path" not in serialized


def test_queries_do_not_mutate_assets_or_locations(database: sqlite3.Connection) -> None:
    asset_id = _asset(database, 1)
    root_id = _root(database, 101)
    _location(database, 201, asset_id, root_id)
    before_changes = database.total_changes
    before = tuple(database.iterdump())

    queries = GalleryQueries(database)
    queries.list_assets()
    queries.get_asset_details(asset_id)

    assert database.total_changes == before_changes
    assert tuple(database.iterdump()) == before


def _thumbnail_fixture(asset_id: str, thumbnail_id: str, cache_name: str = "fixture.png"):
    return SyntheticThumbnailFixture(
        id=thumbnail_id,
        asset_id=asset_id,
        variant=ThumbnailVariant.GRID_256,
        cache_name=cache_name,
        media_type="image/png",
    )


def test_synthetic_thumbnail_hit_and_miss(tmp_path: Path) -> None:
    asset_id = _id(1)
    thumbnail_id = _id(2)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "fixture.png").write_bytes(b"synthetic-png")
    store = SyntheticThumbnailStore(cache, (_thumbnail_fixture(asset_id, thumbnail_id),))

    reference = store.get_reference(asset_id, ThumbnailVariant.GRID_256)
    content = store.open(reference.id)

    assert content.data == b"synthetic-png"
    assert store.get_reference(_id(3), ThumbnailVariant.GRID_256) is None
    with pytest.raises(ThumbnailNotFoundError):
        store.open(_id(999))


def test_gallery_item_can_expose_synthetic_thumbnail_reference(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    asset_id = _asset(database, 1)
    thumbnail_id = _id(2)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "fixture.png").write_bytes(b"synthetic-png")
    store = SyntheticThumbnailStore(cache, (_thumbnail_fixture(asset_id, thumbnail_id),))

    item = GalleryQueries(database, thumbnail_store=store).list_assets().items[0]

    assert item.thumbnail.id == thumbnail_id
    assert "fixture.png" not in repr(item)


@pytest.mark.parametrize("unsafe_name", ["../outside.png", "/tmp/outside.png", "a/b.png", ".."])
def test_thumbnail_fixture_rejects_traversal(tmp_path: Path, unsafe_name: str) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()

    with pytest.raises(InvalidThumbnailError):
        SyntheticThumbnailStore(cache, (_thumbnail_fixture(_id(1), _id(2), unsafe_name),))


def test_thumbnail_rejects_symlink(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    (cache / "fixture.png").symlink_to(outside)
    store = SyntheticThumbnailStore(cache, (_thumbnail_fixture(_id(1), _id(2)),))

    with pytest.raises(UnsafeThumbnailPathError):
        store.open(_id(2))


def test_thumbnail_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    os.mkfifo(cache / "fixture.png")
    store = SyntheticThumbnailStore(cache, (_thumbnail_fixture(_id(1), _id(2)),))

    with pytest.raises(UnsafeThumbnailPathError, match="not a regular file"):
        store.open(_id(2))


def test_thumbnail_rejects_symlink_cache_root(tmp_path: Path) -> None:
    real_cache = tmp_path / "real-cache"
    real_cache.mkdir()
    cache_link = tmp_path / "cache-link"
    cache_link.symlink_to(real_cache, target_is_directory=True)

    with pytest.raises(UnsafeThumbnailPathError):
        SyntheticThumbnailStore(cache_link, ())


def test_thumbnail_size_limit(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "fixture.png").write_bytes(b"12345")
    store = SyntheticThumbnailStore(cache, (_thumbnail_fixture(_id(1), _id(2)),), max_bytes=4)

    with pytest.raises(ThumbnailTooLargeError):
        store.open(_id(2))


def test_thumbnail_store_never_writes_library(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    original = library / "photo.jpg"
    original.write_bytes(b"original")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "fixture.png").write_bytes(b"thumb")
    store = SyntheticThumbnailStore(cache, (_thumbnail_fixture(_id(1), _id(2)),))
    before = tuple((path.name, path.read_bytes()) for path in library.iterdir())

    store.open(_id(2))

    assert tuple((path.name, path.read_bytes()) for path in library.iterdir()) == before
