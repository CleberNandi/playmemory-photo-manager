import { useEffect, useState } from "react";
import { requestThumbnail } from "./thumbnails";
import { AvailabilityIndicator } from "./AvailabilityIndicator";
import type { GalleryItem } from "./types";
function getDisplayName(item: GalleryItem): string { return item.annotation.title?.trim() || item.representative_location?.relative_path.trim() || "Sem título"; }
export function MediaCard({ item }: { item: GalleryItem }) {
  const [thumbnail, setThumbnail] = useState<{id: string; url: string} | null>(null);
  useEffect(() => requestThumbnail(item.asset_id, (url) => setThumbnail(url ? {id: item.asset_id, url} : null)), [item.asset_id]);
  const url = thumbnail?.id === item.asset_id ? thumbnail.url : null;
  const name = getDisplayName(item); const mediaLabel = item.kind === "video" ? "Vídeo" : "Foto";
  return <article className="media-card" role="listitem">
    <div className="media-placeholder" aria-hidden="true">{url && <img className="synthetic-thumbnail" src={url} alt="" onError={() => setThumbnail(null)} />}<svg style={url ? {visibility: "hidden"} : undefined} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5">{item.kind === "video" ? <><rect x="8" y="11" width="32" height="26" rx="4" /><path d="m21 18 10 6-10 6z" /></> : <><rect x="7" y="10" width="34" height="28" rx="4" /><circle cx="17" cy="19" r="3" /><path d="m10 34 9-9 6 6 5-5 8 8" /></>}</svg><span className="media-kind">{url ? `${mediaLabel} · Sintética` : mediaLabel}</span></div>
    <div className="media-card-body"><h3 title={name}>{name}</h3><span className="sr-only">{mediaLabel}{url ? " — ilustração sintética de demonstração" : " — miniatura indisponível"}</span><AvailabilityIndicator availability={item.availability} /><p className="card-metadata">{item.media_type ?? "Formato desconhecido"}{item.annotation.favorite ? " · Favorito" : ""}{item.annotation.rating != null ? ` · ${item.annotation.rating}/5` : ""}</p></div>
  </article>;
}
