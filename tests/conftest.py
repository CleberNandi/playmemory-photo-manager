from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator

import pytest

from playmemories_photo_manager.catalog import initialize_database


@pytest.fixture
def database(tmp_path) -> Iterator[sqlite3.Connection]:
    connection = initialize_database(tmp_path / "catalog.sqlite3")
    yield connection
    connection.close()


@pytest.fixture
def asset_id(database: sqlite3.Connection) -> str:
    identifier = str(uuid.uuid4())
    database.execute("INSERT INTO asset(id, kind) VALUES (?, 'photo')", (identifier,))
    return identifier


@pytest.fixture
def root_id(database: sqlite3.Connection) -> str:
    identifier = str(uuid.uuid4())
    database.execute(
        "INSERT INTO library_root(id, display_name, normalized_path) "
        "VALUES (?, 'Photos', '/media/photos')",
        (identifier,),
    )
    return identifier
