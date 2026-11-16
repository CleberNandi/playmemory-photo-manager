"""Catalog-wide capture navigation, preserving floating dates and explicit precision."""

from __future__ import annotations

import re
from datetime import date, datetime

from .availability import EXCLUDE_MISSING_SQL

EFFECTIVE_CAPTURE_SQL = """COALESCE(
    capture_bucket(a.captured_local_value, a.captured_precision),
    (
        SELECT mtime_bucket(fl.observed_mtime_ns)
        FROM file_location fl
        JOIN library_root lr ON lr.id = fl.library_root_id
        WHERE fl.asset_id = a.id
          AND fl.observed_mtime_ns IS NOT NULL
          AND (? = 0 OR fl.availability <> 'missing' OR lr.availability = 'offline')
        ORDER BY
          CASE
            WHEN fl.entry_type = 'file'
              AND fl.availability = 'present'
              AND lr.availability = 'available' THEN 0
            WHEN fl.availability = 'offline' OR lr.availability = 'offline' THEN 1
            WHEN fl.availability = 'moved_candidate' THEN 2
            ELSE 3
          END,
          fl.library_root_id,
          fl.normalized_relative_path,
          fl.id
        LIMIT 1
    )
)"""


def capture_key(value, precision):
    if not isinstance(value, str):
        return None
    length = {"year": 4, "month": 7, "day": 10, "minute": 10, "second": 10}.get(precision)
    if length is None:
        return None
    key = value[:length]
    try:
        if not re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", key):
            return None
        parts = [int(part) for part in key.split("-")]
        date(*((parts + [1, 1])[:3]))
        return key
    except (ValueError, TypeError):
        return None


def mtime_key(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1_000_000_000).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return None


def created_key(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return capture_key(value[:10], "day")


def validate_period(value):
    if value is None or value == "undated":
        return value
    if not isinstance(value, str) or len(value) not in (4, 7, 10):
        raise ValueError("invalid capture period")
    if capture_key(value, {4: "year", 7: "month", 10: "day"}[len(value)]) != value:
        raise ValueError("invalid capture period")
    return value


def validate_date_filter(value):
    if value is None:
        return None
    if value == "undated":
        raise ValueError("invalid capture period")
    return validate_period(value)


def summary(connection, period=None, *, exclude_missing=False):
    if type(exclude_missing) is not bool:
        raise ValueError("exclude_missing must be boolean")
    # A single read snapshot keeps counts consistent under another catalog writer.
    connection.execute("SAVEPOINT capture_calendar")
    try:
        return _summary(connection, period, exclude_missing)
    finally:
        connection.execute("RELEASE SAVEPOINT capture_calendar")


def _summary(connection, period, exclude_missing):
    validate_period(period)
    if period == "undated" or (period and len(period) == 10):
        raise ValueError("summary expects year, month, or all years")
    connection.create_function("capture_bucket", 2, capture_key, deterministic=True)
    connection.create_function("mtime_bucket", 1, mtime_key, deterministic=True)
    size = 4 if period is None else len(period) + 3
    scope = (
        f"WITH visible_assets AS (SELECT a.* FROM asset a WHERE {EXCLUDE_MISSING_SQL}), "
        f"captures AS (SELECT {EFFECTIVE_CAPTURE_SQL} AS k FROM visible_assets a)"
    )
    rows = connection.execute(
        f"""{scope} SELECT substr(k,1,?) AS bucket,count(*) AS count FROM captures
        WHERE k IS NOT NULL AND (? IS NULL OR substr(k,1,length(?))=?) AND length(k)>=?
        GROUP BY bucket ORDER BY bucket""",
        (exclude_missing, exclude_missing, size, period, period, period, size),
    ).fetchall()
    undated = connection.execute(
        f"{scope} SELECT count(*) FROM captures WHERE k IS NULL",
        (exclude_missing, exclude_missing),
    ).fetchone()[0]
    partial = (
        0
        if period is None
        else connection.execute(
            f"{scope} SELECT count(*) FROM captures WHERE k=?",
            (exclude_missing, exclude_missing, period),
        ).fetchone()[0]
    )
    return {
        "period": period,
        "buckets": [[row[0], row[1]] for row in rows],
        "undated": undated,
        "partial": partial,
    }
