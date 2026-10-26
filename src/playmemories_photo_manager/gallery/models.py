"""Immutable UI-facing projections for gallery reads."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from playmemories_photo_manager.catalog import (
    Annotation,
    AssetKind,
    EntryType,
    HashState,
    LocationAvailability,
    RootAvailability,
    Tag,
)


class AssetAvailability(StrEnum):
    AVAILABLE = "available"
    OFFLINE = "offline"
    UNAVAILABLE = "unavailable"
    NO_LOCATION = "no_location"


class MetadataState(StrEnum):
    NOT_EXTRACTED = "not_extracted"
    EXTRACTED = "extracted"


class TimezoneState(StrEnum):
    UNKNOWN = "unknown"
    OFFSET = "offset"
    NAMED = "named"


class ThumbnailVariant(StrEnum):
    GRID_256 = "grid_256"
    VIEWER_1024 = "viewer_1024"


@dataclass(frozen=True, slots=True)
class GalleryQuery:
    page_size: int = 50
    after: str | None = None
    kind: AssetKind | None = None
    root_id: str | None = None
    availability: AssetAvailability | None = None


@dataclass(frozen=True, slots=True)
class CaptureProjection:
    local_value: str
    precision: str
    timezone_state: TimezoneState
    offset_minutes: int | None
    timezone_name: str | None
    source_kind: str
    metadata_id: str | None
    selection_reason: str | None


@dataclass(frozen=True, slots=True)
class AnnotationSummary:
    rating: int | None
    favorite: bool
    title: str | None


@dataclass(frozen=True, slots=True)
class LocationSummary:
    id: str
    library_root_id: str
    root_display_name: str
    relative_path: str
    entry_type: EntryType
    availability: LocationAvailability
    root_availability: RootAvailability
    observed_byte_size: int | None
    observed_mtime_ns: int | None
    last_seen_at: str | None


@dataclass(frozen=True, slots=True)
class ThumbnailReference:
    id: str
    asset_id: str
    variant: ThumbnailVariant
    media_type: str


@dataclass(frozen=True, slots=True)
class GalleryItem:
    asset_id: str
    kind: AssetKind
    media_type: str | None
    byte_size: int | None
    created_at: str
    captured: CaptureProjection | None
    annotation: AnnotationSummary
    representative_location: LocationSummary | None
    location_count: int
    availability: AssetAvailability
    thumbnail: ThumbnailReference | None = None


@dataclass(frozen=True, slots=True)
class GalleryPage:
    items: tuple[GalleryItem, ...]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True, slots=True)
class AssetSummary:
    id: str
    kind: AssetKind
    sha256: str | None
    hash_state: HashState
    byte_size: int | None
    media_type: str | None
    status: str
    created_at: str


@dataclass(frozen=True, slots=True)
class MetadataObservation:
    id: str
    namespace: str
    key: str
    source: str
    source_key: str
    raw_value: str
    interpreted_value: str | None
    value_type: str
    temporal_local_value: str | None
    temporal_precision: str | None
    timezone_state: TimezoneState | None
    utc_offset_minutes: int | None
    timezone_name: str | None
    extractor_version: str
    extracted_at: str
    parse_error: str | None
    conflict_group: str | None
    is_conflicting: bool


@dataclass(frozen=True, slots=True)
class AssetDetails:
    asset: AssetSummary
    capture: CaptureProjection | None
    annotation: Annotation | None
    tags: tuple[Tag, ...]
    metadata: tuple[MetadataObservation, ...]
    metadata_state: MetadataState
    locations: tuple[LocationSummary, ...]
    locations_truncated: bool
    availability: AssetAvailability


@dataclass(frozen=True, slots=True)
class SyntheticThumbnailFixture:
    id: str
    asset_id: str
    variant: ThumbnailVariant
    cache_name: str
    media_type: str


@dataclass(frozen=True, slots=True)
class ThumbnailContent:
    reference: ThumbnailReference
    data: bytes
