"""Capture observations from an already confined descriptor, never an inferred timezone."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import uuid4


def extract_capture(source):
    from PIL import Image

    try:
        source.seek(0)
        with Image.open(source) as image:
            exif = image.getexif()
            values = dict(exif)
            if 34665 in exif:
                values.update(exif.get_ifd(34665))
            result = []
            for tag, offset_tag, name in (
                (36867, 36881, "DateTimeOriginal"),
                (36868, 36882, "DateTimeDigitized"),
            ):
                if tag not in values:
                    continue
                raw = str(values[tag])
                offset_raw = str(values[offset_tag]) if offset_tag in values else None
                if len(raw) > 256 or (offset_raw is not None and len(offset_raw) > 32):
                    continue  # Oversized metadata is not published as a truncated observation.
                local = offset = None
                error = None
                try:
                    if not re.fullmatch(r"\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}", raw):
                        raise ValueError
                    local = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").isoformat()
                except ValueError:
                    error = "invalid_capture_value"
                if offset_raw is not None and re.fullmatch(
                    r"[+-](?:0\d|1[0-4]):[0-5]\d", offset_raw
                ):
                    offset = (int(offset_raw[1:3]) * 60 + int(offset_raw[4:])) * (
                        -1 if offset_raw[0] == "-" else 1
                    )
                    if abs(offset) > 840:
                        offset = None
                    # Invalid offsets are preserved separately; do not invent one.
                result.append((name, raw, local, offset, offset_raw, error))
            return tuple(result)
    except (OSError, ValueError, SyntaxError, KeyError, TypeError):
        return ()


def persist_capture(connection, registrations, captures):
    """Called only within the same catalog registration transaction; new Assets only."""
    for registration in registrations:
        if registration.disposition.value != "created":
            continue
        asset_id = registration.asset.id
        observations = captures.get(registration.location.normalized_relative_path, ())
        selected = False
        for name, raw, local, offset, offset_raw, error in observations:
            identifier = str(uuid4())
            connection.execute(
                """INSERT INTO metadata(id, asset_id, namespace, metadata_key, source, source_key,
                raw_value, interpreted_value, value_type, temporal_local_value, temporal_precision,
                timezone_state, utc_offset_minutes, extractor_version, extracted_at, parse_error)
                VALUES (?, ?, 'exif', ?, 'embedded-exif', ?, ?, ?, 'datetime', ?, ?, ?, ?,
                'pillow-capture/1', strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?)""",
                (
                    identifier,
                    asset_id,
                    name,
                    name,
                    raw,
                    local,
                    local,
                    "second" if local else None,
                    ("offset" if offset is not None else "unknown") if local else None,
                    offset if local else None,
                    error,
                ),
            )
            if offset_raw is not None:
                connection.execute(
                    """INSERT INTO metadata(id,asset_id,namespace,metadata_key,source,source_key,
                    raw_value,extractor_version,extracted_at) VALUES (?,?,'exif',?,
                    'embedded-exif',?,?,'pillow-capture/1',strftime('%Y-%m-%dT%H:%M:%fZ','now'))""",
                    (
                        str(uuid4()),
                        asset_id,
                        "OffsetTimeOriginal"
                        if name == "DateTimeOriginal"
                        else "OffsetTimeDigitized",
                        "OffsetTime",
                        offset_raw,
                    ),
                )
            if local and not selected:
                connection.execute(
                    """UPDATE asset SET captured_local_value=?,captured_precision='second',
                    captured_timezone_state=?,captured_offset_minutes=?,captured_source_kind='metadata',
                    captured_metadata_id=?,captured_selection_reason=? WHERE id=?""",
                    (
                        local,
                        "offset" if offset is not None else "unknown",
                        offset,
                        identifier,
                        name,
                        asset_id,
                    ),
                )
                selected = True
