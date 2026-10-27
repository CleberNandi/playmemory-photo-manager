CREATE TABLE exact_duplicate_decision (
    id TEXT PRIMARY KEY CHECK (is_uuid(id) = 1),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    keep_location_id TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    evidence_fingerprint TEXT NOT NULL CHECK (
        length(evidence_fingerprint) = 64 AND evidence_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'stale')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    stale_at TEXT,
    CHECK ((status = 'stale') = (stale_at IS NOT NULL)),
    FOREIGN KEY (keep_location_id) REFERENCES file_location(id) ON DELETE RESTRICT
) STRICT;

CREATE UNIQUE INDEX uq_exact_duplicate_current_decision
ON exact_duplicate_decision(sha256, byte_size)
WHERE status = 'current';

CREATE TABLE exact_duplicate_decision_member (
    decision_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    library_root_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
    device INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    link_count INTEGER NOT NULL CHECK (link_count > 0),
    PRIMARY KEY (decision_id, location_id),
    FOREIGN KEY (decision_id) REFERENCES exact_duplicate_decision(id) ON DELETE RESTRICT,
    FOREIGN KEY (location_id) REFERENCES file_location(id) ON DELETE RESTRICT,
    FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE RESTRICT,
    FOREIGN KEY (library_root_id) REFERENCES library_root(id) ON DELETE RESTRICT
) WITHOUT ROWID, STRICT;

CREATE INDEX ix_exact_duplicate_decision_member_location
ON exact_duplicate_decision_member(location_id);
