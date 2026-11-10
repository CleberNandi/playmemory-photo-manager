"""Explicit reveal resolves only catalogued, physically unchanged synthetic files."""

from uuid import uuid4

import pytest
from test_real_images_calendar import apply, raster

from playmemories_photo_manager.catalog import Catalog, connect
from playmemories_photo_manager.desktop.libraries import LibraryDispatcher
from playmemories_photo_manager.desktop.media_location import reveal_location
from playmemories_photo_manager.library import LibraryError


@pytest.fixture
def source(tmp_path):
    dispatcher = LibraryDispatcher()
    path = tmp_path / "catalog.sqlite3"
    session = dispatcher.request(
        "library.create", {"path": str(path), "library_handle": str(uuid4())}
    )["session"]["session_id"]
    root = tmp_path / "media"
    root.mkdir()
    image = root / "synthetic.jpg"
    raster(image)
    with connect(path) as connection:
        root_id = Catalog(connection).register_root("Synthetic", str(root)).id
        apply(root, path, connection, root_id)
        asset = connection.execute("SELECT id FROM asset").fetchone()[0]
    yield dispatcher, path, session, root, image, asset
    dispatcher.close()


def test_reveal_is_scoped_and_does_not_modify_original(source):
    dispatcher, _, session, _, image, asset = source
    before = image.read_bytes()
    assert dispatcher.request("asset.reveal", {"session_id": session, "asset_id": asset}) == {
        "path": str(image)
    }
    assert image.read_bytes() == before
    for params in (
        {"session_id": str(uuid4()), "asset_id": asset},
        {"session_id": session, "asset_id": asset, "path": "/invalid"},
        {"session_id": session, "asset_id": "../invalid"},
    ):
        with pytest.raises(LibraryError):
            dispatcher.request("asset.reveal", params)


@pytest.mark.parametrize("change", ["missing", "symlink", "changed", "ancestor"])
def test_reveal_fails_closed_after_physical_change(source, change):
    dispatcher, _, session, root, image, asset = source
    if change == "missing":
        image.unlink()
    elif change == "symlink":
        other = root / "other.jpg"
        image.rename(other)
        image.symlink_to(other)
    elif change == "changed":
        image.write_bytes(b"changed")
    else:
        moved = root.with_name("moved")
        root.rename(moved)
        root.symlink_to(moved, target_is_directory=True)
    with pytest.raises(LibraryError):
        dispatcher.request("asset.reveal", {"session_id": session, "asset_id": asset})


def test_reveal_rejects_catalog_traversal_and_offline_root(source):
    _, path, _, _, _, asset = source
    with connect(path) as connection:
        connection.execute("UPDATE library_root SET availability='offline'")
        with pytest.raises(LibraryError):
            reveal_location(connection, asset)
        connection.execute("UPDATE library_root SET availability='available'")
        # Corrupt input is deliberately injected to exercise the read boundary.
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute("UPDATE file_location SET normalized_relative_path='../outside.jpg'")
        with pytest.raises(LibraryError):
            reveal_location(connection, asset)
