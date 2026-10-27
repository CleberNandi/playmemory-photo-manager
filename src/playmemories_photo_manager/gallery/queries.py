"""Read-only SQLite projections for the MVP gallery."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import PurePosixPath

from playmemories_photo_manager.catalog import (
    Annotation,
    AssetKind,
    EntryType,
    HashState,
    LocationAvailability,
    RootAvailability,
    Tag,
)

from .errors import (
    AssetNotFoundError,
    CatalogReadError,
    InvalidCursorError,
    InvalidGalleryQueryError,
)
from .models import (
    AnnotationSummary,
    AssetAvailability,
    AssetDetails,
    AssetSummary,
    CaptureProjection,
    GalleryItem,
    GalleryPage,
    GalleryQuery,
    LocationSummary,
    MetadataObservation,
    MetadataState,
    ThumbnailReference,
    ThumbnailVariant,
    TimezoneState,
)
from .thumbnails import SyntheticThumbnailStore

MAX_PAGE_SIZE = 100
MAX_DETAIL_LOCATIONS = 100
_CURSOR_VERSION = 1
_MAX_CURSOR_LENGTH = 2048


class GalleryQueries:
    """Compose immutable gallery DTOs without reading media or mutating the catalog."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        thumbnail_store: SyntheticThumbnailStore | None = None,
    ) -> None:
        self._connection = connection
        self._thumbnail_store = thumbnail_store

    def list_assets(self, query: GalleryQuery | None = None) -> GalleryPage:
        query = query or GalleryQuery()
        normalized = _validate_query(query)
        filters = _filter_values(normalized)
        cursor_values = _decode_cursor(normalized.after, filters) if normalized.after else None
        sql = """
            WITH candidates AS (
                SELECT a.*,
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM file_location fl
                            JOIN library_root lr ON lr.id = fl.library_root_id
                            WHERE fl.asset_id = a.id
                              AND fl.entry_type = 'file'
                              AND fl.availability = 'present'
                              AND lr.availability = 'available'
                        ) THEN 'available'
                        WHEN EXISTS (
                            SELECT 1 FROM file_location fl
                            JOIN library_root lr ON lr.id = fl.library_root_id
                            WHERE fl.asset_id = a.id
                              AND (fl.availability = 'offline' OR lr.availability = 'offline')
                        ) THEN 'offline'
                        WHEN EXISTS (SELECT 1 FROM file_location fl WHERE fl.asset_id = a.id)
                            THEN 'unavailable'
                        ELSE 'no_location'
                    END AS projected_availability
                FROM asset a
                WHERE (? IS NULL OR a.kind = ?)
                  AND (? IS NULL OR EXISTS (
                      SELECT 1 FROM file_location fl
                      WHERE fl.asset_id = a.id AND fl.library_root_id = ?
                  ))
            )
            SELECT * FROM candidates
            WHERE (? IS NULL OR projected_availability = ?)
              AND (? IS NULL OR (created_at, id) > (?, ?))
            ORDER BY created_at, id
            LIMIT ?
        """
        after_created, after_id = cursor_values or (None, None)
        parameters = (
            filters["kind"],
            filters["kind"],
            filters["root_id"],
            filters["root_id"],
            filters["availability"],
            filters["availability"],
            after_created,
            after_created,
            after_id,
            normalized.page_size + 1,
        )
        with self._read_snapshot():
            rows = self._connection.execute(sql, parameters).fetchall()
            visible = rows[: normalized.page_size]
            locations = self._locations_by_asset(row["id"] for row in visible)
            annotations = self._annotations_by_asset(row["id"] for row in visible)

        has_more = len(rows) > normalized.page_size
        items = tuple(
            _gallery_item(
                row,
                locations.get(row["id"], ()),
                annotations.get(row["id"]),
                self._thumbnail_reference(row["id"]),
            )
            for row in visible
        )
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = _encode_cursor(last["created_at"], last["id"], filters)
        return GalleryPage(items=items, next_cursor=next_cursor, has_more=has_more)

    def get_asset_details(self, asset_id: str) -> AssetDetails:
        identifier = _canonical_uuid(asset_id, "asset_id")
        with self._read_snapshot():
            row = self._connection.execute(
                "SELECT * FROM asset WHERE id = ?", (identifier,)
            ).fetchone()
            if row is None:
                raise AssetNotFoundError("asset not found")
            location_rows = self._connection.execute(
                """SELECT fl.*, lr.display_name AS root_display_name,
                    lr.availability AS root_availability
                FROM file_location fl
                JOIN library_root lr ON lr.id = fl.library_root_id
                WHERE fl.asset_id = ?
                ORDER BY fl.library_root_id, fl.normalized_relative_path, fl.id
                LIMIT ?""",
                (identifier, MAX_DETAIL_LOCATIONS + 1),
            ).fetchall()
            annotation_row = self._connection.execute(
                """SELECT asset_id, rating, favorite, title, description, created_at, updated_at
                FROM user_annotation WHERE asset_id = ?""",
                (identifier,),
            ).fetchone()
            metadata_rows = self._connection.execute(
                "SELECT * FROM metadata WHERE asset_id = ? ORDER BY id", (identifier,)
            ).fetchall()
            tag_rows = self._connection.execute(
                """SELECT t.id, t.display_name, t.normalized_key, t.created_at
                FROM tag t JOIN asset_tag at ON at.tag_id = t.id
                WHERE at.asset_id = ? ORDER BY t.id""",
                (identifier,),
            ).fetchall()
            availability = self._asset_availability(identifier)

        projected_locations = tuple(
            _location(item) for item in location_rows[:MAX_DETAIL_LOCATIONS]
        )
        annotation = _annotation(annotation_row) if annotation_row else None
        metadata = tuple(_metadata(item) for item in metadata_rows)
        return AssetDetails(
            asset=_asset_summary(row),
            capture=_capture(row),
            annotation=annotation,
            tags=tuple(Tag(**dict(item)) for item in tag_rows),
            metadata=metadata,
            metadata_state=MetadataState.EXTRACTED if metadata else MetadataState.NOT_EXTRACTED,
            locations=projected_locations,
            locations_truncated=len(location_rows) > MAX_DETAIL_LOCATIONS,
            availability=availability,
        )

    @contextmanager
    def _read_snapshot(self):
        name = "gallery_read_snapshot"
        self._connection.execute(f"SAVEPOINT {name}")
        try:
            yield
        finally:
            self._connection.execute(f"RELEASE SAVEPOINT {name}")

    def _locations_by_asset(
        self, asset_ids: Iterable[str]
    ) -> dict[str, tuple[LocationSummary, ...]]:
        identifiers = tuple(asset_ids)
        if not identifiers:
            return {}
        placeholders = ",".join("?" for _ in identifiers)
        rows = self._connection.execute(
            f"""SELECT fl.*, lr.display_name AS root_display_name,
                lr.availability AS root_availability
            FROM file_location fl
            JOIN library_root lr ON lr.id = fl.library_root_id
            WHERE fl.asset_id IN ({placeholders})
            ORDER BY fl.asset_id, fl.library_root_id, fl.normalized_relative_path, fl.id""",
            identifiers,
        )
        grouped: dict[str, list[LocationSummary]] = {}
        for row in rows:
            grouped.setdefault(row["asset_id"], []).append(_location(row))
        return {key: tuple(value) for key, value in grouped.items()}

    def _annotations_by_asset(self, asset_ids: Iterable[str]) -> dict[str, Annotation]:
        identifiers = tuple(asset_ids)
        if not identifiers:
            return {}
        placeholders = ",".join("?" for _ in identifiers)
        rows = self._connection.execute(
            f"""SELECT asset_id, rating, favorite, title, description, created_at, updated_at
            FROM user_annotation WHERE asset_id IN ({placeholders})""",
            identifiers,
        )
        return {row["asset_id"]: _annotation(row) for row in rows}

    def _asset_availability(self, asset_id: str) -> AssetAvailability:
        row = self._connection.execute(
            """SELECT CASE
                WHEN EXISTS (
                    SELECT 1 FROM file_location fl
                    JOIN library_root lr ON lr.id = fl.library_root_id
                    WHERE fl.asset_id = ? AND fl.availability = 'present'
                      AND fl.entry_type = 'file'
                      AND lr.availability = 'available'
                ) THEN 'available'
                WHEN EXISTS (
                    SELECT 1 FROM file_location fl
                    JOIN library_root lr ON lr.id = fl.library_root_id
                    WHERE fl.asset_id = ?
                      AND (fl.availability = 'offline' OR lr.availability = 'offline')
                ) THEN 'offline'
                WHEN EXISTS (SELECT 1 FROM file_location fl WHERE fl.asset_id = ?)
                    THEN 'unavailable'
                ELSE 'no_location'
            END AS value""",
            (asset_id, asset_id, asset_id),
        ).fetchone()
        return AssetAvailability(row["value"])

    def _thumbnail_reference(self, asset_id: str) -> ThumbnailReference | None:
        if self._thumbnail_store is None:
            return None
        return self._thumbnail_store.get_reference(asset_id, ThumbnailVariant.GRID_256)


def _validate_query(query: GalleryQuery) -> GalleryQuery:
    if isinstance(query.page_size, bool) or not isinstance(query.page_size, int):
        raise InvalidGalleryQueryError("page_size must be an integer")
    if not 1 <= query.page_size <= MAX_PAGE_SIZE:
        raise InvalidGalleryQueryError("page_size must be between 1 and 100")
    try:
        kind = AssetKind(query.kind) if query.kind is not None else None
        availability = (
            AssetAvailability(query.availability) if query.availability is not None else None
        )
    except (ValueError, TypeError) as error:
        raise InvalidGalleryQueryError("unsupported gallery filter") from error
    root_id = _canonical_uuid(query.root_id, "root_id") if query.root_id is not None else None
    if query.after is not None and not isinstance(query.after, str):
        raise InvalidCursorError("cursor must be text")
    return GalleryQuery(query.page_size, query.after, kind, root_id, availability)


def _filter_values(query: GalleryQuery) -> dict[str, str | None]:
    return {
        "kind": query.kind.value if query.kind else None,
        "root_id": query.root_id,
        "availability": query.availability.value if query.availability else None,
    }


def _filter_fingerprint(filters: dict[str, str | None]) -> str:
    encoded = json.dumps(filters, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _encode_cursor(created_at: str, asset_id: str, filters: dict[str, str | None]) -> str:
    payload = {
        "v": _CURSOR_VERSION,
        "c": created_at,
        "i": asset_id,
        "f": _filter_fingerprint(filters),
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    envelope = {"p": payload, "h": hashlib.sha256(payload_bytes).hexdigest()}
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_cursor(cursor: str, filters: dict[str, str | None]) -> tuple[str, str]:
    if not cursor or len(cursor) > _MAX_CURSOR_LENGTH or not cursor.isascii():
        raise InvalidCursorError("invalid cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or set(envelope) != {"p", "h"}:
            raise ValueError
        payload = envelope["p"]
        if not isinstance(payload, dict) or set(payload) != {"v", "c", "i", "f"}:
            raise ValueError
        canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        canonical_cursor = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        if canonical_cursor != cursor:
            raise ValueError
        if envelope["h"] != hashlib.sha256(canonical_payload).hexdigest():
            raise ValueError
        if payload["v"] != _CURSOR_VERSION or payload["f"] != _filter_fingerprint(filters):
            raise ValueError
        if not isinstance(payload["c"], str) or not payload["c"]:
            raise ValueError
        return payload["c"], _canonical_uuid(payload["i"], "cursor asset id")
    except (
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as error:
        raise InvalidCursorError("invalid or incompatible cursor") from error


def _canonical_uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise InvalidGalleryQueryError(f"{field} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise InvalidGalleryQueryError(f"{field} must be a canonical UUID") from error
    if str(parsed) != value:
        raise InvalidGalleryQueryError(f"{field} must be a canonical UUID")
    return value


def _safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        raise CatalogReadError("catalog contains an unsafe relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise CatalogReadError("catalog contains an unsafe relative path")
    return value


def _location(row: sqlite3.Row) -> LocationSummary:
    return LocationSummary(
        id=row["id"],
        library_root_id=row["library_root_id"],
        root_display_name=row["root_display_name"],
        relative_path=_safe_relative_path(row["normalized_relative_path"]),
        entry_type=EntryType(row["entry_type"]),
        availability=LocationAvailability(row["availability"]),
        root_availability=RootAvailability(row["root_availability"]),
        observed_byte_size=row["observed_byte_size"],
        observed_mtime_ns=row["observed_mtime_ns"],
        last_seen_at=row["last_seen_at"],
    )


def _location_rank(location: LocationSummary) -> tuple[int, str, str, str]:
    if (
        location.entry_type is EntryType.FILE
        and location.availability is LocationAvailability.PRESENT
        and location.root_availability is RootAvailability.AVAILABLE
    ):
        rank = 0
    elif (
        location.availability is LocationAvailability.OFFLINE
        or location.root_availability is RootAvailability.OFFLINE
    ):
        rank = 1
    elif location.availability is LocationAvailability.MOVED_CANDIDATE:
        rank = 2
    else:
        rank = 3
    return rank, location.library_root_id, location.relative_path, location.id


def _capture(row: sqlite3.Row) -> CaptureProjection | None:
    if row["captured_local_value"] is None:
        return None
    return CaptureProjection(
        local_value=row["captured_local_value"],
        precision=row["captured_precision"],
        timezone_state=(
            TimezoneState(row["captured_timezone_state"])
            if row["captured_timezone_state"] is not None
            else None
        ),
        offset_minutes=row["captured_offset_minutes"],
        timezone_name=row["captured_timezone_name"],
        source_kind=row["captured_source_kind"],
        metadata_id=row["captured_metadata_id"],
        selection_reason=row["captured_selection_reason"],
    )


def _annotation(row: sqlite3.Row) -> Annotation:
    values = dict(row)
    values["favorite"] = bool(values["favorite"])
    return Annotation(**values)


def _asset_summary(row: sqlite3.Row) -> AssetSummary:
    return AssetSummary(
        id=row["id"],
        kind=AssetKind(row["kind"]),
        sha256=row["sha256"],
        hash_state=HashState(row["hash_state"]),
        byte_size=row["byte_size"],
        media_type=row["media_type"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _metadata(row: sqlite3.Row) -> MetadataObservation:
    return MetadataObservation(
        id=row["id"],
        namespace=row["namespace"],
        key=row["metadata_key"],
        source=row["source"],
        source_key=row["source_key"],
        raw_value=row["raw_value"],
        interpreted_value=row["interpreted_value"],
        value_type=row["value_type"],
        temporal_local_value=row["temporal_local_value"],
        temporal_precision=row["temporal_precision"],
        timezone_state=TimezoneState(row["timezone_state"]) if row["timezone_state"] else None,
        utc_offset_minutes=row["utc_offset_minutes"],
        timezone_name=row["timezone_name"],
        extractor_version=row["extractor_version"],
        extracted_at=row["extracted_at"],
        parse_error=row["parse_error"],
        conflict_group=row["conflict_group"],
        is_conflicting=bool(row["is_conflicting"]),
    )


def _gallery_item(
    row: sqlite3.Row,
    locations: tuple[LocationSummary, ...],
    annotation: Annotation | None,
    thumbnail: ThumbnailReference | None,
) -> GalleryItem:
    representative = min(locations, key=_location_rank) if locations else None
    summary = AnnotationSummary(
        rating=annotation.rating if annotation else None,
        favorite=annotation.favorite if annotation else False,
        title=annotation.title if annotation else None,
    )
    return GalleryItem(
        asset_id=row["id"],
        kind=AssetKind(row["kind"]),
        media_type=row["media_type"],
        byte_size=row["byte_size"],
        created_at=row["created_at"],
        captured=_capture(row),
        annotation=summary,
        representative_location=representative,
        location_count=len(locations),
        availability=AssetAvailability(row["projected_availability"]),
        thumbnail=thumbnail,
    )
