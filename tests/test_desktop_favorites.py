"""Scoped catalog-only favorite commands, persistence and catalog-wide cursors."""

from uuid import uuid4

import pytest
from test_desktop_ingestion import Client

from playmemories_photo_manager.catalog import Catalog, connect
from playmemories_photo_manager.desktop.libraries import LibraryDispatcher
from playmemories_photo_manager.gallery import GalleryQueries, GalleryQuery
from playmemories_photo_manager.gallery.errors import InvalidCursorError
from playmemories_photo_manager.library import LibraryError


@pytest.fixture
def library(tmp_path):
    dispatcher = LibraryDispatcher()
    path = tmp_path / "catalog.sqlite3"
    state = dispatcher.request(
        "library.create", {"path": str(path), "library_handle": str(uuid4())}
    )
    session = state["session"]["session_id"]
    with connect(path) as connection:
        catalog = Catalog(connection)
        assets = [catalog.create_asset("photo").id for _ in range(55)]
        catalog.set_title(assets[-1], "Synthetic title")
        catalog.set_description(assets[-1], "Synthetic description")
        catalog.set_rating(assets[-1], 4)
    yield dispatcher, path, session, assets
    dispatcher.close()


def command(session, asset, favorite=True):
    return {"session_id": session, "asset_id": asset, "favorite": favorite}


def test_favorite_sets_exact_boolean_preserves_other_annotations_and_reopens(library):
    dispatcher, path, session, assets = library
    target = assets[-1]
    before = dispatcher.request("asset.details", {"session_id": session, "asset_id": target})
    for _ in range(2):
        assert dispatcher.request("annotation.favorite", command(session, target)) == {
            "asset_id": target,
            "favorite": True,
        }
    after = dispatcher.request("asset.details", {"session_id": session, "asset_id": target})
    for key in ("title", "description", "rating", "created_at"):
        assert before["annotation"][key] == after["annotation"][key]
    for key in ("asset", "capture", "metadata", "locations", "tags"):
        assert before[key] == after[key]
    assert (
        dispatcher.request("gallery.list", {"session_id": session, "favorites_only": True})[
            "items"
        ][0]["asset_id"]
        == target
    )
    dispatcher.request("library.close", {"session_id": session})
    reopened = dispatcher.request(
        "library.open", {"path": str(path), "library_handle": str(uuid4())}
    )["session"]["session_id"]
    assert reopened != session
    assert (
        dispatcher.request("gallery.list", {"session_id": reopened, "favorites_only": True})[
            "items"
        ][0]["asset_id"]
        == target
    )
    assert (
        dispatcher.request("annotation.favorite", command(reopened, target, False))["favorite"]
        is False
    )
    assert (
        dispatcher.request("gallery.list", {"session_id": reopened, "favorites_only": True})[
            "items"
        ]
        == ()
    )


@pytest.mark.parametrize("favorite", [None, 0, 1, "true", [], {}])
def test_favorite_rejects_non_boolean(library, favorite):
    dispatcher, _, session, assets = library
    with pytest.raises(LibraryError, match="invalid_request"):
        dispatcher.request("annotation.favorite", command(session, assets[0], favorite))


def test_unknown_keys_stale_session_and_missing_asset_never_write(library):
    dispatcher, _, session, assets = library
    for params, code in (
        (command(session, assets[0]) | {"path": "/untrusted"}, "invalid_request"),
        (command(str(uuid4()), assets[0]), "stale_session"),
        (command(session, str(uuid4())), "not_found"),
    ):
        with pytest.raises(LibraryError, match=code):
            dispatcher.request("annotation.favorite", params)
    assert (
        dispatcher.request("gallery.list", {"session_id": session, "favorites_only": True})["items"]
        == ()
    )


def test_favorites_filter_finds_later_assets_and_has_filter_bound_pagination(library):
    dispatcher, path, session, assets = library
    with connect(path) as connection:
        initial = GalleryQueries(connection).list_assets(GalleryQuery(page_size=24))
        initial_ids = {item.asset_id for item in initial.items}
        target = next(asset for asset in assets if asset not in initial_ids)
    dispatcher.request("annotation.favorite", command(session, target))
    result = dispatcher.request("gallery.list", {"session_id": session, "favorites_only": True})
    assert [item["asset_id"] for item in result["items"]] == [target]
    with connect(path) as connection:
        queries = GalleryQueries(connection)
        with pytest.raises(InvalidCursorError):
            queries.list_assets(GalleryQuery(after=initial.next_cursor, favorites_only=True))
    for asset in assets:
        dispatcher.request("annotation.favorite", command(session, asset))
    seen = set()
    after = None
    while True:
        page = dispatcher.request(
            "gallery.list",
            {"session_id": session, "favorites_only": True, "page_size": 24, "after": after},
        )
        ids = {item["asset_id"] for item in page["items"]}
        assert not ids & seen
        seen |= ids
        if not page["has_more"]:
            break
        after = page["next_cursor"]
    assert seen == set(assets)


def test_locked_catalog_fails_without_mutating_or_retrying(library):
    dispatcher, path, session, assets = library
    with connect(path) as other:
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(LibraryError, match="outcome_unknown"):
            dispatcher.request("annotation.favorite", command(session, assets[0]))
        other.rollback()
    assert (
        dispatcher.request("gallery.list", {"session_id": session, "favorites_only": True})["items"]
        == ()
    )


def test_favorite_command_over_authenticated_pipe_and_rejects_paths(library):
    dispatcher, path, session, assets = library
    dispatcher.request("library.close", {"session_id": session})
    client = Client(enabled=False)
    try:
        state = client.request("library.open", {"path": str(path), "library_handle": str(uuid4())})
        scoped = command(state["result"]["session"]["session_id"], assets[0])
        assert client.request("annotation.favorite", scoped)["result"]["favorite"] is True
        assert (
            client.request("annotation.favorite", scoped | {"path": "/untrusted"})["error"]["code"]
            == "invalid_request"
        )
        assert (
            client.request(
                "gallery.list", {"session_id": scoped["session_id"], "favorites_only": 1}
            )["error"]["code"]
            == "invalid_request"
        )
    finally:
        client.close()


def test_annotation_edits_persist_and_reuse_normalized_tags(library):
    dispatcher, path, session, assets = library
    asset, other = assets[-1], assets[0]

    def edit(target, field, value):
        return dispatcher.request(
            "annotation.edit",
            {"session_id": session, "asset_id": target, "field": field, "value": value},
        )

    dispatcher.request("annotation.favorite", command(session, asset))
    edit(asset, "rating", 5)
    edit(asset, "title", "Novo título")
    edit(asset, "description", "Descrição de teste")
    edit(asset, "tag_add", "  Viagem de férias  ")
    edit(asset, "tag_add", "VIAGEM DE FÉRIAS")
    edit(other, "tag_add", "viagem de férias")
    with connect(path) as connection:
        catalog = Catalog(connection)
        tags = catalog.list_asset_tags(asset)
        assert len(tags) == 1
        assert catalog.list_asset_tags(other) == tags
    with pytest.raises(LibraryError) as failure:
        edit(asset, "rating", True)
    assert failure.value.code == "invalid_request"
    edit(other, "tag_remove", tags[0].id)
    dispatcher.request("library.close", {"session_id": session})
    session = dispatcher.request(
        "library.open", {"path": str(path), "library_handle": str(uuid4())}
    )["session"]["session_id"]
    details = dispatcher.request("asset.details", {"session_id": session, "asset_id": asset})
    assert details["annotation"]["rating"] == 5
    assert details["annotation"]["title"] == "Novo título"
    assert details["annotation"]["description"] == "Descrição de teste"
    assert details["annotation"]["favorite"] is True
    assert [tag["display_name"] for tag in details["tags"]] == ["Viagem de férias"]
    assert not dispatcher.request("asset.details", {"session_id": session, "asset_id": other})[
        "tags"
    ]


def test_album_membership_scopes_pages_and_survives_reopening(library):
    dispatcher, path, session, assets = library

    def action(operation, **params):
        return dispatcher.request(
            "album.action", {"session_id": session, "action": operation, **params}
        )

    album = action("create", name=" Viagem ")
    album_id = album["id"]
    assert album["name"] == "Viagem"
    assert action("list", offset=0) == {"albums": [album], "next_offset": None}
    assert action("add", album_id=album_id, asset_id=assets[0]) == {"changed": True}
    assert action("add", album_id=album_id, asset_id=assets[0]) == {"changed": False}
    assert action("add", album_id=album_id, asset_id=assets[-1]) == {"changed": True}
    with pytest.raises(LibraryError, match="not_found"):
        action("add", album_id=album_id, asset_id=str(uuid4()))
    with pytest.raises(LibraryError, match="invalid_request"):
        action("list", offset=True)
    with pytest.raises(LibraryError, match="invalid_request"):
        action("create", name="  ")
    with connect(path) as connection:
        queries = GalleryQueries(connection)
        first = queries.list_assets(GalleryQuery(album_id=album_id, page_size=1))
        second = queries.list_assets(GalleryQuery(album_id=album_id, after=first.next_cursor))
        assert {item.asset_id for item in (*first.items, *second.items)} == {assets[0], assets[-1]}
        with pytest.raises(InvalidCursorError):
            queries.list_assets(GalleryQuery(after=first.next_cursor))
    old_session = session
    dispatcher.request("library.close", {"session_id": session})
    session = dispatcher.request(
        "library.open", {"path": str(path), "library_handle": str(uuid4())}
    )["session"]["session_id"]
    assert action("list", offset=0)["albums"] == [album]
    with pytest.raises(LibraryError, match="stale_session"):
        dispatcher.request(
            "album.action", {"session_id": old_session, "action": "list", "offset": 0}
        )
    assert action("remove", album_id=album_id, asset_id=assets[0]) == {"changed": True}
    scoped = dispatcher.request("gallery.list", {"session_id": session, "album_id": album_id})
    assert [item["asset_id"] for item in scoped["items"]] == [assets[-1]]
    assert dispatcher.request("asset.details", {"session_id": session, "asset_id": assets[0]})


def test_deleting_album_preserves_original_and_other_membership(library, tmp_path):
    dispatcher, path, session, assets = library
    asset_id = assets[0]
    original = tmp_path / "photo.jpg"
    original.write_bytes(b"synthetic original")
    with connect(path) as connection:
        catalog = Catalog(connection)
        root = catalog.register_root("Synthetic", str(tmp_path))
        location = catalog.register_location(
            asset_id, root.id, original.name, last_seen_at="2026-11-11T00:00:00Z"
        )
        removed = catalog.create_album("Remove")
        retained = catalog.create_album("Keep")
        for album in (removed, retained):
            catalog.add_asset_to_album(album.id, asset_id)

    params = {"session_id": session, "action": "delete", "album_id": removed.id}
    with pytest.raises(LibraryError, match="invalid_request"):
        dispatcher.request("album.action", {**params, "asset_id": asset_id})
    assert dispatcher.request("album.action", params) == {"changed": True}
    assert dispatcher.request("album.action", params) == {"changed": False}
    dispatcher.request("library.close", {"session_id": session})
    with connect(path) as connection:
        catalog = Catalog(connection)
        assert catalog.list_albums() == [retained]
        assert [asset.id for asset in catalog.list_album_assets(retained.id)] == [asset_id]
        assert catalog.get_asset_locations(asset_id) == [location]
        assert connection.execute("SELECT count(*) FROM album_asset").fetchone()[0] == 1
    assert original.read_bytes() == b"synthetic original"
