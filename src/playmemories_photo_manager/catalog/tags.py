"""Unicode-aware tag operations that SQLite cannot express portably."""

from __future__ import annotations

import sqlite3
import unicodedata
import uuid


def normalize_tag(display_name: str) -> str:
    """Return the canonical NFKC/whitespace/casefold tag key."""
    normalized = unicodedata.normalize("NFKC", display_name)
    return " ".join(normalized.split()).casefold()


def create_tag(
    connection: sqlite3.Connection, display_name: str, *, tag_id: str | None = None
) -> str:
    """Create a tag while guaranteeing that its persisted key matches its name."""
    key = normalize_tag(display_name)
    if not key:
        raise ValueError("tag name must not be empty after normalization")
    identifier = tag_id or str(uuid.uuid4())
    with connection:
        connection.execute(
            "INSERT INTO tag(id, display_name, normalized_key) VALUES (?, ?, ?)",
            (identifier, display_name, key),
        )
    return identifier
