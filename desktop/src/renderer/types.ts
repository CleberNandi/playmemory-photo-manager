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

export type PhotoFilters = {
  keyword?: string;
  tag_id?: string;
  rating?: number;
  media_type?: string;
  camera?: string;
  lens?: string;
};
export type Facet = "tags" | "types" | "cameras" | "lenses";
export type FilterOption = {id:string; name:string};
export type FilterOptionsPage = {options:FilterOption[]; next_offset:number|null};
export type PhotoFacets = {
  more?: Facet[];
  tags: {id:string; name:string}[];
  types: string[];
  cameras: string[];
  lenses: string[];
};

export interface GalleryPage {
  facets?: PhotoFacets;
  roots?: {id: string; name: string}[];
  items: GalleryItem[];
  next_cursor: string | null;
  has_more: boolean;
}

export type AnnotationField = "rating" | "title" | "description" | "tag_add" | "tag_remove";

declare global {
  interface Window {
    photoManager?: {
      getIndexStatus?():Promise<{state:string;busy:boolean;revision:number;added_count:number;error:string|null;last_check:number|null}>;
      refreshFolders?():Promise<unknown>;
      onGalleryChanged?(listener:()=>void):()=>void;
      chooseMediaRoot?(sessionId: string): Promise<unknown>;
      prepareCataloging?(sessionId: string, rootGrantId: string, recursive: boolean): Promise<unknown>;
      getPreparationStatus?(sessionId: string, operationId: string): Promise<unknown>;
      cancelPreparation?(sessionId: string, operationId: string): Promise<unknown>;
      listCatalogingCandidates?(sessionId: string, proposalId: string, cursor: string | null, pageSize: number): Promise<unknown>;
      applyCataloging?(sessionId: string, proposalId: string, candidateIds: string[]): Promise<unknown>;
      getCatalogingApplicationStatus?(sessionId: string, commandId: string): Promise<unknown>;
      openManagedLibrary?():Promise<LibraryState>;
      addMediaFolder?(id:string):Promise<unknown>;
      getFolderImportStatus?(id:string,job:string):Promise<unknown>;
      stopFolderImport?(id:string,job:string):Promise<unknown>;
      getLibraryState?(): Promise<LibraryState>;
      chooseCreateLibrary?(): Promise<LibraryState>;
      chooseOpenLibrary?(): Promise<LibraryState>;
      closeLibrary?(sessionId: string): Promise<LibraryState>;
      setReopenLibrary?(value: boolean): Promise<LibraryState>;
      forgetLibrary?(): Promise<LibraryState>;
      listFilterOptions?(facet: Facet, keyword: string, offset: number): Promise<FilterOptionsPage>;
      listAlbums?(offset: number): Promise<{albums: Album[]; next_offset: number | null}>;
      createAlbum?(name: string): Promise<Album>;
      changeAlbumMembership?(albumId: string, assetId: string, action: "add" | "remove"): Promise<{changed: boolean}>;
      listGallery(params?: { pageSize?: number; after?: string | null; capturePeriod?: string | null; favoritesOnly?: boolean; rootId?: string; albumId?: string; filters?: PhotoFilters }): Promise<GalleryPage>;
      saveRotation?(assetId:string,angle:number,mode:"replace"|"copy"):Promise<ImageSaveJob>;
      getImageSaveStatus?(jobId:string):Promise<ImageSaveJob>;
      showMediaMenu?(assetId:string):Promise<"view"|"properties"|"favorite"|null>;
      locateMedia?(assetId:string,describe?:boolean):Promise<{status:string}>;
      getAssetDetails?(assetId: string): Promise<DetailsResult>;
      setFavorite?(assetId: string, favorite: boolean): Promise<{asset_id: string; favorite: boolean}>;
      getCalendar?(period: string | null): Promise<{period: string | null; buckets: [string,number][]; undated:number; partial:number}>;
      editAnnotation?(assetId: string, field: AnnotationField, value: string | number | null): Promise<unknown>;
      getPreview?(assetId: string, variant?: "dimensions" | "original", offset?: number): Promise<unknown>;
      getThumbnail?(assetId: string): Promise<unknown>;
      listDuplicates?(params?: DuplicateListParams): Promise<DuplicateResult<DuplicateListPage>>;
      getDuplicateGroup?(params: DuplicateGroupParams): Promise<DuplicateResult<DuplicateGroupPage>>;
      onBackendReset?(listener: () => void): () => void;
      retryGallery(): Promise<GalleryPage>;
    };
  }
}

export interface LibraryState {
  cataloging_enabled?: boolean;
  folder_import_enabled?:boolean;
  state: "active" | "no_library" | "unavailable" | "demo";
  session: {session_id: string; library_handle: string; generation: number; display_name: string} | null;
  reopen: boolean;
  error?: string;
  warning?: string;
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

export interface ImageSaveJob {job_id:string;asset_id:string;state:string;result_asset_id:string|null;error:string|null}

export type Album = {id: string; name: string};
