export type Availability = "available" | "offline" | "unavailable" | "no_location";

export interface GalleryItem {
  asset_id: string;
  kind: "photo" | "video";
  media_type: string | null;
  created_at: string;
  availability: Availability;
  annotation: { rating: number | null; favorite: boolean; title: string | null };
  representative_location: { relative_path: string; root_display_name: string } | null;
}

export interface GalleryPage {
  items: GalleryItem[];
  next_cursor: string | null;
  has_more: boolean;
}

declare global {
  interface Window {
    photoManager?: {
      listGallery(params?: { pageSize?: number; after?: string | null }): Promise<GalleryPage>;
      getAssetDetails?(assetId: string): Promise<DetailsResult>;
      getThumbnail?(assetId: string): Promise<unknown>;
      listDuplicates?(params?: DuplicateListParams): Promise<DuplicateResult<DuplicateListPage>>;
      getDuplicateGroup?(params: DuplicateGroupParams): Promise<DuplicateResult<DuplicateGroupPage>>;
      onBackendReset?(listener: () => void): () => void;
      retryGallery(): Promise<GalleryPage>;
    };
  }
}

// Transport projection of the existing Python AssetDetails; no persistence model.
export interface CaptureProjection {
  local_value: string; precision: string; timezone_state: string | null;
  offset_minutes: number | null; timezone_name: string | null;
  source_kind: string; metadata_id: string | null; selection_reason: string | null;
}
export interface AssetDetails {
  asset: {id: string; kind: string; sha256: string | null; hash_state: string; byte_size: number | null; media_type: string | null; status: string; created_at: string};
  capture: CaptureProjection | null;
  annotation: {asset_id: string; title: string | null; description: string | null; favorite: boolean; rating: number | null; created_at: string; updated_at: string} | null;
  tags: {id: string; display_name: string; normalized_key: string; created_at: string}[];
  metadata_state: "not_extracted" | "extracted";
  metadata: {id: string; namespace: string; key: string; source: string; source_key: string; raw_value: string; interpreted_value: string | null; value_type: string; temporal_local_value: string | null; temporal_precision: string | null; timezone_state: string | null; utc_offset_minutes: number | null; timezone_name: string | null; extractor_version: string; extracted_at: string; parse_error: string | null; conflict_group: string | null; is_conflicting: boolean}[];
  locations: {id: string; library_root_id: string; root_display_name: string; relative_path: string; entry_type: string; availability: string; root_availability: string; observed_byte_size: number | null; observed_mtime_ns: string | null; last_seen_at: string | null}[];
  locations_truncated: boolean;
  availability: Availability;
}
export type DetailsResult = {status: "ready"; details: AssetDetails} | {status: "not_found" | "invalid_request" | "temporarily_unavailable" | "internal_error"};

export interface DuplicateMember {
  asset_id: string; location_id: string; library_root_id: string;
  root_display_name: string; relative_path: string;
  location_source: "catalog_fixture" | "projection_fixture";
  hardlinked: boolean; identity_conflict: boolean; protected: boolean | null; blocks: string[];
}
export interface DuplicateGroup {
  group_key: string; sha256: string; byte_size: string; evidence_fingerprint: string | null;
  occurrence_count: number; physical_copy_count: number; blocks: string[];
  plan_state: "pending" | "ready" | "blocked" | "stale" | null;
  review: {decision_id: string; status: "current" | "stale"; keep_location_id: string; reason: string} | null;
}
export interface DuplicatePage {
  version: 1; snapshot_id: string; source: "synthetic_fixture"; observed_at: null; freshness: "synthetic";
  coverage: "complete" | "partial" | "unavailable";
  issues: {kind: string; asset_id: string; location_id: string; library_root_id: string; relative_path: string}[];
  eligible_location_count: number; hashed_location_count: number;
  total_count: number; next_cursor: string | null;
}
export interface DuplicateListPage extends DuplicatePage {groups: DuplicateGroup[]}
export interface DuplicateGroupPage extends DuplicatePage {group: DuplicateGroup; members: DuplicateMember[]}
export type DuplicateResult<P> = {status: "ready"; page: P} | {status: "analysis_not_available" | "temporarily_unavailable" | "internal_error" | "invalid_request" | "stale_snapshot" | "not_found" | "response_too_large"};
export interface DuplicateListParams {pageSize?: number; after?: string | null}
export interface DuplicateGroupParams extends DuplicateListParams {snapshotId: string; groupKey: string}
