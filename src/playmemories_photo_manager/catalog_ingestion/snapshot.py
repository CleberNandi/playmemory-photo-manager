"""Bounded worker snapshot: the returned value owns no connection or filesystem handle."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from ..catalog import Catalog
from ..catalog.repository import CatalogRepository
from ..change_planning import CatalogSnapshot
from ..library import LibraryError, read_library_connection
from ..scanner import ScanScope
from .service import _snapshot_read_version


@dataclass(frozen=True, slots=True)
class SnapshotLimits:
    max_locations: int = 2000
    max_bytes: int = 8 * 1024 * 1024

    def __post_init__(self):
        for value, maximum in ((self.max_locations, 2000), (self.max_bytes, 8 * 1024 * 1024)):
            if type(value) is not int or not 0 < value <= maximum:
                raise ValueError("invalid snapshot budget")


class SnapshotResourceLimitError(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__("resource_limit")


class _ByteBudget:
    def __init__(self, limit: int):
        self.limit = limit
        # Upper bound for keys, brackets, scope, read_version and separators.
        self.used = 512
        self.encoder = json.JSONEncoder(ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    def add(self, item):
        for chunk in self.encoder.iterencode(asdict(item)):
            self.used += len(chunk.encode("utf-8"))
            if self.used > self.limit:
                raise SnapshotResourceLimitError("max_bytes")
        self.used += 1  # Comma between records.
        if self.used > self.limit:
            raise SnapshotResourceLimitError("max_bytes")


def capture_catalog_snapshot(
    path: Path, root_id: str, *, limits: SnapshotLimits | None = None
) -> CatalogSnapshot:
    """Read the whole registered root consistently, then close before any media I/O.

    No scan, validation of media or transaction survives this function. Root selection
    and authorization are the responsibility of the future preparation controller.
    """
    limits = SnapshotLimits() if limits is None else limits
    if not isinstance(limits, SnapshotLimits):
        raise TypeError("limits must be SnapshotLimits")
    budget = _ByteBudget(limits.max_bytes)
    try:
        with read_library_connection(path, max_value_bytes=limits.max_bytes) as connection:
            connection.execute("BEGIN")
            try:
                catalog = Catalog(connection)
                repository = CatalogRepository(connection)
                root = catalog.get_root(root_id)
                budget.add(root)
                locations = []
                offset = 0
                while True:
                    # Bound each page, including the single excess-row sentinel.
                    page_size = min(100, limits.max_locations - len(locations) + 1)
                    loaded = 0
                    for location in repository.iter_root_locations(root_id, page_size, offset):
                        loaded += 1
                        if len(locations) == limits.max_locations:
                            raise SnapshotResourceLimitError("max_locations")
                        budget.add(location)
                        locations.append(location)
                    if loaded < page_size:
                        break
                    offset += loaded
                assets = []
                asset_ids = tuple(sorted({item.asset_id for item in locations}))
                for start in range(0, len(asset_ids), 100):
                    loaded = 0
                    batch = asset_ids[start : start + 100]
                    for asset in repository.iter_assets(batch):
                        loaded += 1
                        budget.add(asset)
                        assets.append(asset)
                    if loaded != len(batch):
                        raise LibraryError("corrupt")
                assets = tuple(assets)
                locations = tuple(locations)
                return CatalogSnapshot(
                    root,
                    assets,
                    locations,
                    (),
                    ScanScope(".", recursive=True, follows_links=False),
                    _snapshot_read_version(root, assets, locations),
                )
            finally:
                connection.rollback()
    except LibraryError as error:
        if error.code == "resource_limit":
            raise SnapshotResourceLimitError("max_bytes") from None
        raise
    except Exception as error:
        # Catalog wraps SQLite read errors. Preserve unrelated failures unchanged.
        cause = error
        while cause is not None:
            if getattr(cause, "sqlite_errorcode", 0) & 255 == sqlite3.SQLITE_TOOBIG:
                raise SnapshotResourceLimitError("max_bytes") from None
            cause = cause.__cause__
        raise
