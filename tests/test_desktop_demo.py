"""Demo isolation, reproducibility and production gallery cursor integration."""

import sqlite3
from uuid import UUID

import pytest

from playmemories_photo_manager.desktop.bridge import _dispatch
from playmemories_photo_manager.desktop.demo import DEMO_ASSET_COUNT, open_demo_catalog


def test_demo_is_reproducible_readonly_and_paginates_without_loss():
    first = open_demo_catalog()
    second = open_demo_catalog()
    try:
        assert first.execute("PRAGMA database_list").fetchone()[2] == ""
        assert first.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert first.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in ("asset", "file_location", "library_root", "user_annotation"):
            assert [tuple(row) for row in first.execute(f"SELECT * FROM {table}")] == [
                tuple(row) for row in second.execute(f"SELECT * FROM {table}")
            ]
        expected = [row[0] for row in first.execute("SELECT id FROM asset ORDER BY created_at, id")]
        assert all(UUID(value).version == 4 for value in expected)
        seen = []
        availability = set()
        cursor = None
        sizes = []
        while True:
            page = _dispatch(first, "gallery.list", {"page_size": 24, "after": cursor})
            seen.extend(item["asset_id"] for item in page["items"])
            availability.update(item["availability"] for item in page["items"])
            sizes.append(len(page["items"]))
            if not page["has_more"]:
                assert page["next_cursor"] is None
                break
            assert cursor != page["next_cursor"]
            cursor = page["next_cursor"]
        assert seen == expected
        assert len(set(seen)) == DEMO_ASSET_COUNT
        assert sizes == [24, 24, 24, 1]
        assert availability == {"available", "offline", "unavailable", "no_location"}
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            first.execute("DELETE FROM asset")
    finally:
        first.close()
        second.close()


def test_demo_bootstrap_never_opens_a_catalog_path(monkeypatch):
    from playmemories_photo_manager.desktop import bridge

    monkeypatch.setattr("sys.argv", ["bridge", "--demo"])
    monkeypatch.setenv("PLAYMEMORIES_BRIDGE_TOKEN", "a" * 32)

    def forbidden(_path):
        pytest.fail("demo attempted to open a filesystem catalog")

    def inspect(connection, _token, *, demo=False):
        assert demo
        assert len(_dispatch(connection, "gallery.list", {})["items"]) == 24
        return 0

    monkeypatch.setattr(bridge.LibrarySession, "open", forbidden)
    monkeypatch.setattr(bridge, "serve", inspect)
    assert bridge.main() == 0


def test_demo_cannot_be_combined_with_catalog_path(monkeypatch):
    from playmemories_photo_manager.desktop import bridge

    monkeypatch.setattr("sys.argv", ["bridge", "--demo", "--catalog", "synthetic.sqlite"])
    with pytest.raises(SystemExit) as error:
        bridge.main()
    assert error.value.code == 2
