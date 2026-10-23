from __future__ import annotations

import sqlite3
import uuid

import pytest

from playmemories_photo_manager.catalog import (
    AssetKind,
    Catalog,
    DuplicateAssociationError,
    EntryType,
    HashState,
    InvalidInputError,
    InvalidReferenceError,
    InvariantViolationError,
    LocationAvailability,
    NotFoundError,
    PersistenceError,
    RootAvailability,
    UniquenessConflictError,
)


@pytest.fixture
def catalog(database: sqlite3.Connection) -> Catalog:
    return Catalog(database)


def test_create_asset_generates_uuid_and_does_not_require_location(catalog: Catalog) -> None:
    asset = catalog.create_asset(AssetKind.PHOTO)
    assert str(uuid.UUID(asset.id)) == asset.id
    assert asset.kind is AssetKind.PHOTO
    assert catalog.get_asset_locations(asset.id) == []


def test_distinct_assets_can_share_hash(catalog: Catalog) -> None:
    digest = "a" * 64
    first = catalog.create_asset("photo", sha256=digest, hash_state=HashState.VERIFIED)
    second = catalog.create_asset("photo", sha256=digest, hash_state=HashState.VERIFIED)
    assert first.id != second.id
    assert first.sha256 == second.sha256


def test_asset_lookup_and_validation(catalog: Catalog) -> None:
    with pytest.raises(NotFoundError):
        catalog.get_asset(str(uuid.uuid4()))
    with pytest.raises(InvalidInputError):
        catalog.get_asset("not-a-uuid")
    with pytest.raises(InvalidInputError):
        catalog.create_asset("photo", sha256="A" * 64, hash_state="verified")


def test_asset_listing_is_deterministic_and_limited(catalog: Catalog) -> None:
    identifiers = [catalog.create_asset("photo").id for _ in range(4)]
    assert [asset.id for asset in catalog.list_assets(limit=2)] == sorted(identifiers)[:2]
    assert [asset.id for asset in catalog.list_assets(limit=2, offset=2)] == sorted(identifiers)[2:]
    with pytest.raises(InvalidInputError):
        catalog.list_assets(limit=101)


def test_root_registration_lookup_listing_and_duplicate(catalog: Catalog) -> None:
    root = catalog.register_root("Photos", "/catalog/photos")
    assert catalog.get_root(root.id) == root
    assert catalog.list_roots() == [root]
    with pytest.raises(UniquenessConflictError):
        catalog.register_root("Duplicate", "/catalog/photos")


def test_location_registration_and_multiple_locations(catalog: Catalog) -> None:
    asset = catalog.create_asset("photo")
    root = catalog.register_root("Photos", "/catalog/photos")
    first = catalog.register_location(
        asset.id,
        root.id,
        "2026/first.jpg",
        last_seen_at="2026-10-23T12:00:00Z",
        filesystem_id="dev:42",
    )
    second = catalog.register_location(
        asset.id,
        root.id,
        "2026/hardlink.jpg",
        last_seen_at="2026-10-23T12:00:00Z",
        filesystem_id="dev:42",
    )
    assert catalog.get_location(first.id) == first
    assert catalog.get_asset_locations(asset.id) == sorted(
        [first, second], key=lambda item: item.id
    )
    assert (
        catalog.list_root_locations(root.id, limit=1)
        == sorted([first, second], key=lambda item: item.id)[:1]
    )


def test_location_references_and_active_path_are_enforced(catalog: Catalog) -> None:
    asset = catalog.create_asset("photo")
    root = catalog.register_root("Photos", "/catalog/photos")
    arguments = (asset.id, root.id, "same.jpg")
    catalog.register_location(*arguments, last_seen_at="2026-10-23T12:00:00Z")
    with pytest.raises(UniquenessConflictError):
        catalog.register_location(*arguments, last_seen_at="2026-10-23T12:01:00Z")
    with pytest.raises(InvalidReferenceError):
        catalog.register_location(
            str(uuid.uuid4()), root.id, "other.jpg", last_seen_at="2026-10-23T12:00:00Z"
        )
    with pytest.raises(InvalidReferenceError):
        catalog.register_location(
            asset.id, str(uuid.uuid4()), "other.jpg", last_seen_at="2026-10-23T12:00:00Z"
        )


@pytest.mark.parametrize("state", list(LocationAvailability))
def test_location_states_are_accepted_with_consistent_root(
    catalog: Catalog, state: LocationAvailability
) -> None:
    asset = catalog.create_asset("photo")
    root_state = (
        RootAvailability.OFFLINE
        if state is LocationAvailability.OFFLINE
        else RootAvailability.AVAILABLE
    )
    root = catalog.register_root(state, f"/roots/{state}", availability=root_state)
    location = catalog.register_location(
        asset.id,
        root.id,
        f"{state}.jpg",
        availability=state,
        last_seen_at="2026-10-23T12:00:00Z",
    )
    assert location.availability is state


def test_location_rejects_unsafe_path_and_unfounded_state(catalog: Catalog) -> None:
    asset = catalog.create_asset("photo")
    root = catalog.register_root("Offline", "/offline", availability="offline")
    with pytest.raises(InvalidInputError):
        catalog.register_location(asset.id, root.id, "../escape.jpg", last_seen_at="now")
    with pytest.raises(InvariantViolationError):
        catalog.register_location(
            asset.id, root.id, "unknown.jpg", availability="missing", last_seen_at="now"
        )
    with pytest.raises(InvalidInputError):
        catalog.register_location(
            asset.id,
            root.id,
            "link.jpg",
            entry_type=EntryType.SYMLINK,
            last_seen_at="now",
        )


def test_album_membership_is_idempotent_and_removable(catalog: Catalog) -> None:
    asset = catalog.create_asset("photo")
    album = catalog.create_album("Trip", description="2026")
    assert catalog.get_album(album.id) == album
    assert catalog.list_albums() == [album]
    assert catalog.add_asset_to_album(album.id, asset.id) is True
    assert catalog.add_asset_to_album(album.id, asset.id) is False
    assert catalog.list_album_assets(album.id) == [asset]
    assert catalog.remove_asset_from_album(album.id, asset.id) is True
    assert catalog.remove_asset_from_album(album.id, asset.id) is False


def test_asset_can_belong_to_multiple_albums(catalog: Catalog) -> None:
    asset = catalog.create_asset("photo")
    albums = [catalog.create_album(name) for name in ("One", "Two")]
    for album in albums:
        catalog.add_asset_to_album(album.id, asset.id)
        assert catalog.list_album_assets(album.id) == [asset]


def test_tag_normalization_uniqueness_and_association(catalog: Catalog) -> None:
    asset = catalog.create_asset("photo")
    cafe = catalog.create_tag(" CAFÉ ")
    plain = catalog.create_tag("cafe")
    assert cafe.normalized_key == "café"
    assert plain.normalized_key == "cafe"
    with pytest.raises(UniquenessConflictError):
        catalog.create_tag("café")
    catalog.add_tag_to_asset(asset.id, cafe.id)
    with pytest.raises(DuplicateAssociationError):
        catalog.add_tag_to_asset(asset.id, cafe.id)
    assert catalog.list_asset_tags(asset.id) == [cafe]
    assert catalog.remove_tag_from_asset(asset.id, cafe.id) is True
    assert catalog.remove_tag_from_asset(asset.id, cafe.id) is False


def test_annotation_partial_updates_and_explicit_clearing(catalog: Catalog) -> None:
    asset = catalog.create_asset("photo")
    assert catalog.get_annotation(asset.id) is None
    catalog.set_title(asset.id, "Title")
    catalog.set_description(asset.id, "Description")
    catalog.set_rating(asset.id, 5)
    annotation = catalog.set_favorite(asset.id, True)
    assert (annotation.title, annotation.description, annotation.rating, annotation.favorite) == (
        "Title",
        "Description",
        5,
        True,
    )
    cleared = catalog.set_title(asset.id, None)
    assert cleared.title is None
    assert (cleared.description, cleared.rating, cleared.favorite) == ("Description", 5, True)


@pytest.mark.parametrize("rating", [0, 6, 2.5, True])
def test_annotation_rejects_invalid_rating(catalog: Catalog, rating: object) -> None:
    asset = catalog.create_asset("photo")
    with pytest.raises(InvalidInputError):
        catalog.set_rating(asset.id, rating)  # type: ignore[arg-type]


def test_annotation_does_not_modify_metadata(
    catalog: Catalog, database: sqlite3.Connection
) -> None:
    asset = catalog.create_asset("photo")
    metadata_id = str(uuid.uuid4())
    database.execute(
        """INSERT INTO metadata(
            id, asset_id, namespace, metadata_key, source, source_key, raw_value,
            extractor_version, extracted_at
        ) VALUES (?, ?, 'xmp', 'title', 'sidecar', 'dc:title', 'Original', 'test/1', 'now')""",
        (metadata_id, asset.id),
    )
    catalog.set_title(asset.id, "Catalog title")
    assert (
        database.execute("SELECT raw_value FROM metadata WHERE id = ?", (metadata_id,)).fetchone()[
            0
        ]
        == "Original"
    )


def test_failed_write_rolls_back_and_hides_sqlite_error(
    catalog: Catalog, database: sqlite3.Connection
) -> None:
    database.executescript(
        """CREATE TABLE write_probe(value TEXT);
        CREATE TRIGGER fail_album AFTER INSERT ON album BEGIN
            INSERT INTO write_probe(value) VALUES (NEW.name);
            SELECT RAISE(FAIL, 'sensitive sqlite detail');
        END;"""
    )
    with pytest.raises(PersistenceError, match="unexpected catalog persistence failure") as caught:
        catalog.create_album("Must roll back")
    assert "sensitive" not in str(caught.value)
    assert database.execute("SELECT count(*) FROM album").fetchone()[0] == 0
    assert database.execute("SELECT count(*) FROM write_probe").fetchone()[0] == 0


def test_catalog_rejects_unmanaged_connection() -> None:
    connection = sqlite3.connect(":memory:")
    with pytest.raises(InvalidInputError, match="managed connection"):
        Catalog(connection)
    connection.close()
