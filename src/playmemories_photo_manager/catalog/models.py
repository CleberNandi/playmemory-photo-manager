"""Typed values returned by the catalog application layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AssetKind(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"


class HashState(StrEnum):
    ABSENT = "absent"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class RootAvailability(StrEnum):
    AVAILABLE = "available"
    OFFLINE = "offline"


class LocationAvailability(StrEnum):
    PRESENT = "present"
    OFFLINE = "offline"
    MISSING = "missing"
    MOVED_CANDIDATE = "moved_candidate"


class EntryType(StrEnum):
    FILE = "file"
    SYMLINK = "symlink"


class FileRegistrationDisposition(StrEnum):
    CREATED = "created"
    ALREADY_EXISTS = "already_exists"


@dataclass(frozen=True, slots=True)
class Asset:
    id: str
    kind: AssetKind
    sha256: str | None
    hash_state: HashState
    byte_size: int | None
    media_type: str | None
    status: str
    created_at: str


@dataclass(frozen=True, slots=True)
class LibraryRoot:
    id: str
    display_name: str
    normalized_path: str
    availability: RootAvailability
    created_at: str
    last_checked_at: str | None


@dataclass(frozen=True, slots=True)
class FileLocation:
    id: str
    asset_id: str
    library_root_id: str
    normalized_relative_path: str
    entry_type: EntryType
    symlink_target: str | None
    filesystem_id: str | None
    observed_byte_size: int | None
    observed_mtime_ns: int | None
    availability: LocationAvailability
    last_seen_at: str | None


@dataclass(frozen=True, slots=True)
class NewFileRegistration:
    relative_path: str
    kind: AssetKind
    byte_size: int
    media_type: str | None
    filesystem_id: str | None
    observed_mtime_ns: int | None


@dataclass(frozen=True, slots=True)
class FileRegistrationResult:
    disposition: FileRegistrationDisposition
    asset: Asset
    location: FileLocation


@dataclass(frozen=True, slots=True)
class Album:
    id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class Tag:
    id: str
    display_name: str
    normalized_key: str
    created_at: str


@dataclass(frozen=True, slots=True)
class Annotation:
    asset_id: str
    rating: int | None
    favorite: bool
    title: str | None
    description: str | None
    created_at: str
    updated_at: str
