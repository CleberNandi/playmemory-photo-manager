CREATE TABLE schema_migration (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    name TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE TABLE metadata (
    id TEXT PRIMARY KEY CHECK (is_uuid(id) = 1),
    asset_id TEXT NOT NULL,
    namespace TEXT NOT NULL CHECK (namespace IN ('exif', 'xmp', 'iptc', 'container', 'filesystem', 'catalog')),
    metadata_key TEXT NOT NULL CHECK (length(metadata_key) > 0),
    source TEXT NOT NULL CHECK (length(source) > 0),
    source_key TEXT NOT NULL CHECK (length(source_key) > 0),
    raw_value TEXT NOT NULL,
    interpreted_value TEXT,
    value_type TEXT NOT NULL DEFAULT 'text' CHECK (value_type IN ('text', 'integer', 'real', 'boolean', 'datetime', 'json')),
    temporal_local_value TEXT,
    temporal_precision TEXT CHECK (temporal_precision IS NULL OR temporal_precision IN ('second', 'minute', 'day', 'month', 'year', 'unknown')),
    timezone_state TEXT CHECK (timezone_state IS NULL OR timezone_state IN ('unknown', 'offset', 'named')),
    utc_offset_minutes INTEGER CHECK (utc_offset_minutes IS NULL OR utc_offset_minutes BETWEEN -840 AND 840),
    timezone_name TEXT,
    extractor_version TEXT NOT NULL CHECK (length(extractor_version) > 0),
    extracted_at TEXT NOT NULL,
    parse_error TEXT,
    conflict_group TEXT,
    is_conflicting INTEGER NOT NULL DEFAULT 0 CHECK (is_conflicting IN (0, 1)),
    UNIQUE (id, asset_id),
    CHECK ((temporal_local_value IS NULL) = (temporal_precision IS NULL)),
    CHECK (temporal_local_value IS NOT NULL OR timezone_state IS NULL),
    CHECK ((timezone_state = 'offset') = (utc_offset_minutes IS NOT NULL)),
    CHECK ((timezone_state = 'named') = (timezone_name IS NOT NULL)),
    CHECK (timezone_state IS NOT NULL OR timezone_name IS NULL),
    FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE
) STRICT;

CREATE TABLE asset (
    id TEXT PRIMARY KEY CHECK (is_uuid(id) = 1),
    kind TEXT NOT NULL CHECK (kind IN ('photo', 'video')),
    sha256 TEXT CHECK (sha256 IS NULL OR (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*')),
    hash_state TEXT NOT NULL DEFAULT 'absent' CHECK (hash_state IN ('absent', 'unverified', 'verified')),
    byte_size INTEGER CHECK (byte_size IS NULL OR byte_size >= 0),
    media_type TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    captured_local_value TEXT,
    captured_offset_minutes INTEGER CHECK (captured_offset_minutes IS NULL OR captured_offset_minutes BETWEEN -840 AND 840),
    captured_timezone_state TEXT CHECK (captured_timezone_state IS NULL OR captured_timezone_state IN ('unknown', 'offset', 'named')),
    captured_timezone_name TEXT,
    captured_precision TEXT CHECK (captured_precision IS NULL OR captured_precision IN ('second', 'minute', 'day', 'month', 'year', 'unknown')),
    captured_source_kind TEXT NOT NULL DEFAULT 'none' CHECK (captured_source_kind IN ('none', 'metadata', 'manual')),
    captured_metadata_id TEXT,
    captured_selection_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((sha256 IS NULL AND hash_state = 'absent') OR (sha256 IS NOT NULL AND hash_state <> 'absent')),
    CHECK ((captured_local_value IS NULL) = (captured_precision IS NULL)),
    CHECK ((captured_source_kind = 'none') = (captured_local_value IS NULL)),
    CHECK ((captured_source_kind = 'metadata') = (captured_metadata_id IS NOT NULL)),
    CHECK (captured_local_value IS NOT NULL OR captured_timezone_state IS NULL),
    CHECK ((captured_timezone_state = 'offset') = (captured_offset_minutes IS NOT NULL)),
    CHECK ((captured_timezone_state = 'named') = (captured_timezone_name IS NOT NULL)),
    CHECK (captured_timezone_state IS NOT NULL OR captured_timezone_name IS NULL),
    FOREIGN KEY (captured_metadata_id, id) REFERENCES metadata(id, asset_id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE library_root (
    id TEXT PRIMARY KEY CHECK (is_uuid(id) = 1),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    normalized_path TEXT NOT NULL UNIQUE CHECK (length(normalized_path) > 0),
    availability TEXT NOT NULL DEFAULT 'available' CHECK (availability IN ('available', 'offline')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_checked_at TEXT
) STRICT;

CREATE TABLE file_location (
    id TEXT PRIMARY KEY CHECK (is_uuid(id) = 1),
    asset_id TEXT NOT NULL,
    library_root_id TEXT NOT NULL,
    normalized_relative_path TEXT NOT NULL CHECK (length(normalized_relative_path) > 0 AND substr(normalized_relative_path, 1, 1) <> '/'),
    entry_type TEXT NOT NULL DEFAULT 'file' CHECK (entry_type IN ('file', 'symlink')),
    symlink_target TEXT,
    filesystem_id TEXT,
    observed_byte_size INTEGER CHECK (observed_byte_size IS NULL OR observed_byte_size >= 0),
    observed_mtime_ns INTEGER CHECK (observed_mtime_ns IS NULL OR observed_mtime_ns >= 0),
    availability TEXT NOT NULL DEFAULT 'present' CHECK (availability IN ('present', 'missing', 'offline', 'moved_candidate')),
    last_seen_at TEXT,
    CHECK ((entry_type = 'symlink') = (symlink_target IS NOT NULL)),
    FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE RESTRICT,
    FOREIGN KEY (library_root_id) REFERENCES library_root(id) ON DELETE RESTRICT
) STRICT;

CREATE UNIQUE INDEX uq_file_location_active_path
ON file_location(library_root_id, normalized_relative_path)
WHERE availability <> 'missing';
CREATE INDEX ix_file_location_asset ON file_location(asset_id);
CREATE INDEX ix_file_location_root_availability ON file_location(library_root_id, availability);
CREATE INDEX ix_file_location_filesystem_id ON file_location(library_root_id, filesystem_id)
WHERE filesystem_id IS NOT NULL;

CREATE TABLE album (
    id TEXT PRIMARY KEY CHECK (is_uuid(id) = 1),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE TABLE album_asset (
    album_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    position INTEGER CHECK (position IS NULL OR position >= 0),
    added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (album_id, asset_id),
    FOREIGN KEY (album_id) REFERENCES album(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE
) WITHOUT ROWID, STRICT;
CREATE INDEX ix_album_asset_asset ON album_asset(asset_id);

CREATE TABLE tag (
    id TEXT PRIMARY KEY CHECK (is_uuid(id) = 1),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    normalized_key TEXT NOT NULL UNIQUE CHECK (
        length(normalized_key) > 0 AND normalized_key = normalize_tag(display_name)
    ),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE TABLE asset_tag (
    asset_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'user' CHECK (origin IN ('user', 'imported')),
    added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (asset_id, tag_id),
    FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tag(id) ON DELETE CASCADE
) WITHOUT ROWID, STRICT;
CREATE INDEX ix_asset_tag_tag ON asset_tag(tag_id);

CREATE TABLE user_annotation (
    asset_id TEXT PRIMARY KEY,
    rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
    title TEXT,
    description TEXT,
    corrected_local_value TEXT,
    corrected_precision TEXT CHECK (corrected_precision IS NULL OR corrected_precision IN ('second', 'minute', 'day', 'month', 'year', 'unknown')),
    corrected_timezone_state TEXT CHECK (corrected_timezone_state IS NULL OR corrected_timezone_state IN ('unknown', 'offset', 'named')),
    corrected_offset_minutes INTEGER CHECK (corrected_offset_minutes IS NULL OR corrected_offset_minutes BETWEEN -840 AND 840),
    corrected_timezone_name TEXT,
    correction_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((corrected_local_value IS NULL) = (corrected_precision IS NULL)),
    CHECK (corrected_local_value IS NOT NULL OR corrected_timezone_state IS NULL),
    CHECK ((corrected_timezone_state = 'offset') = (corrected_offset_minutes IS NOT NULL)),
    CHECK ((corrected_timezone_state = 'named') = (corrected_timezone_name IS NOT NULL)),
    CHECK (corrected_timezone_state IS NOT NULL OR corrected_timezone_name IS NULL),
    FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE
) WITHOUT ROWID, STRICT;

CREATE TABLE thumbnail (
    id TEXT PRIMARY KEY CHECK (is_uuid(id) = 1),
    asset_id TEXT NOT NULL,
    variant TEXT NOT NULL CHECK (length(variant) > 0),
    cache_relative_path TEXT NOT NULL UNIQUE CHECK (length(cache_relative_path) > 0 AND substr(cache_relative_path, 1, 1) <> '/'),
    generator_version TEXT NOT NULL CHECK (length(generator_version) > 0),
    source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) > 0),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (asset_id, variant, generator_version),
    FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE
) STRICT;
CREATE INDEX ix_thumbnail_asset ON thumbnail(asset_id);

CREATE INDEX ix_asset_sha256 ON asset(sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX ix_asset_capture ON asset(captured_local_value) WHERE captured_local_value IS NOT NULL;
CREATE INDEX ix_metadata_asset_key ON metadata(asset_id, namespace, metadata_key);
CREATE INDEX ix_metadata_conflict ON metadata(asset_id, conflict_group)
WHERE is_conflicting = 1;

CREATE TRIGGER prevent_asset_id_update
BEFORE UPDATE OF id ON asset
BEGIN
    SELECT RAISE(ABORT, 'asset id is immutable');
END;
