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
      getThumbnail?(assetId: string): Promise<unknown>;
      retryGallery(): Promise<GalleryPage>;
    };
  }
}
