"""Catalog-wide capture navigation, preserving floating dates and explicit precision."""

from __future__ import annotations

import re
from datetime import date


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


def validate_period(value):
    if value is None or value == "undated":
        return value
    if not isinstance(value, str) or len(value) not in (4, 7, 10):
        raise ValueError("invalid capture period")
    if capture_key(value, {4: "year", 7: "month", 10: "day"}[len(value)]) != value:
        raise ValueError("invalid capture period")
    return value


def summary(connection, period=None):
    # A single read snapshot keeps counts consistent under another catalog writer.
    connection.execute("SAVEPOINT capture_calendar")
    try:
        return _summary(connection, period)
    finally:
        connection.execute("RELEASE SAVEPOINT capture_calendar")


def _summary(connection, period):
    validate_period(period)
    if period == "undated" or (period and len(period) == 10):
        raise ValueError("summary expects year, month, or all years")
    connection.create_function("capture_bucket", 2, capture_key, deterministic=True)
    size = 4 if period is None else len(period) + 3
    rows = connection.execute(
        """WITH captures AS (SELECT capture_bucket(captured_local_value, captured_precision) AS k
        FROM asset) SELECT substr(k,1,?) AS bucket,count(*) AS count FROM captures
        WHERE k IS NOT NULL AND (? IS NULL OR substr(k,1,length(?))=?) AND length(k)>=?
        GROUP BY bucket ORDER BY bucket""",
        (size, period, period, period, size),
    ).fetchall()
    undated = connection.execute(
        "SELECT count(*) FROM asset WHERE "
        "capture_bucket(captured_local_value,captured_precision) IS NULL"
    ).fetchone()[0]
    partial = (
        0
        if period is None
        else connection.execute(
            "SELECT count(*) FROM asset WHERE "
            "capture_bucket(captured_local_value,captured_precision)=?",
            (period,),
        ).fetchone()[0]
    )
    return {
        "period": period,
        "buckets": [[row[0], row[1]] for row in rows],
        "undated": undated,
        "partial": partial,
    }
