"""Isolated synthetic fixture; never opens a catalog or media path supplied by callers."""

from __future__ import annotations

import random
import sqlite3
from uuid import UUID

from playmemories_photo_manager.catalog import Catalog, initialize_database
from playmemories_photo_manager.catalog.models import (
    AssetKind,
    EntryType,
    FileLocation,
    HashState,
    LocationAvailability,
    RootAvailability,
)
from playmemories_photo_manager.catalog.repository import CatalogRepository

DEMO_ASSET_COUNT = 73
DEMO_TIME = "2026-01-01T12:00:00.000Z"


def open_demo_catalog() -> sqlite3.Connection:
    """Build a fresh SQLite fixture, then lock the connection to read-only queries.

    Seeded v4 fixture identifiers are independent of paths/content. This fixture
    uses the existing repository for historical states lacking a public write
    use case; it does not extend the production identity or transition contracts.
    """
    connection = initialize_database(":memory:")
    rng = random.Random(20261029)

    def identifier() -> str:
        return str(UUID(int=rng.getrandbits(128), version=4))

    repository = CatalogRepository(connection)
    catalog = Catalog(connection)
    try:
        roots = [identifier(), identifier()]
        connection.execute("BEGIN IMMEDIATE")
        for index, root_id in enumerate(roots):
            repository.insert_root(
                root_id,
                ("Demonstração local", "Volume sintético offline")[index],
                f"/synthetic-demo/volume-{index}",
                (RootAvailability.AVAILABLE, RootAvailability.OFFLINE)[index],
            )
        assets = []
        for index in range(DEMO_ASSET_COUNT):
            asset_id = identifier()
            assets.append(asset_id)
            video = index % 5 == 0
            repository.insert_asset(
                asset_id,
                AssetKind.VIDEO if video else AssetKind.PHOTO,
                None,
                HashState.ABSENT,
                1024 * (index + 1),
                "video/mp4" if video else "image/jpeg",
            )
            state = index % 4
            if state == 3:
                continue  # An Asset can legitimately have no known location.
            repository.insert_location(
                FileLocation(
                    id=identifier(),
                    asset_id=asset_id,
                    library_root_id=roots[1 if state == 1 else 0],
                    normalized_relative_path=f"amostra-{index + 1:03}.{'mp4' if video else 'jpg'}",
                    entry_type=EntryType.FILE,
                    symlink_target=None,
                    filesystem_id=None,
                    observed_byte_size=1024 * (index + 1),
                    observed_mtime_ns=None,
                    availability=(
                        LocationAvailability.PRESENT,
                        LocationAvailability.OFFLINE,
                        LocationAvailability.MISSING,
                    )[state],
                    last_seen_at=DEMO_TIME,
                )
            )
        connection.commit()
        for index, asset_id in enumerate(assets):
            catalog.set_title(asset_id, f"Amostra sintética {index + 1:03}")
            catalog.set_favorite(asset_id, index % 7 == 0)
            catalog.set_rating(asset_id, None if index % 3 == 0 else index % 5 + 1)
        # Fixed historical timestamps deliberately exercise UUID tie-breaking.
        for table in ("asset", "library_root", "user_annotation"):
            connection.execute(f"UPDATE {table} SET created_at = ?", (DEMO_TIME,))
        connection.execute("UPDATE user_annotation SET updated_at = ?", (DEMO_TIME,))
        connection.execute("PRAGMA query_only = ON")
        return connection
    except Exception:
        connection.close()
        raise
