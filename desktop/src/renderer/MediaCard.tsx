import {mediaMenu} from "./media-menu";
import { useEffect, useState } from "react";
import { FavoriteButton } from "./FavoriteButton";
import { requestThumbnail } from "./thumbnails";
import { AvailabilityIndicator } from "./AvailabilityIndicator";
import type { GalleryItem } from "./types";
function getDisplayName(item: GalleryItem): string { return item.annotation.title?.trim() || item.representative_location?.relative_path.trim().split("/").pop() || "Sem título"; }
export function MediaCard({ item, selected = false, onSelect, onOpen, onFavoriteChanged }: { item: GalleryItem; selected?: boolean; onSelect?: (button: HTMLButtonElement) => void; onOpen?: (rotation?:number) => void; onFavoriteChanged?: (favorite:boolean)=>void }) {
  const [menuError,setMenuError]=useState(false);
  const [thumbnail, setThumbnail] = useState<{id: string; url: string} | null>(null);
  useEffect(() => requestThumbnail(item.asset_id, (url) => setThumbnail(url ? {id: item.asset_id, url} : null)), [item.asset_id]);
  const url = thumbnail?.id === item.asset_id ? thumbnail.url : null;
  const location = item.representative_location;
  const parent = location?.relative_path.split("/").slice(0, -1).join("/");
  const folder = location && [location.root_display_name, parent].filter(Boolean).join(" / ");
  const name = getDisplayName(item); const mediaLabel = item.kind === "video" ? "Vídeo" : "Foto";
  return <article className="media-card" role="listitem" onContextMenu={event=>{setMenuError(false);void mediaMenu(event,item.asset_id,onSelect,onOpen,()=>setMenuError(true));}} onKeyDown={event=>{if(event.key==="ContextMenu"||(event.shiftKey&&event.key==="F10")){setMenuError(false);void mediaMenu(event,item.asset_id,onSelect,onOpen,()=>setMenuError(true));}}}>
    {menuError&&<p role="alert">Não foi possível executar a ação. Confira se a imagem e a biblioteca continuam disponíveis.</p>}
    <div className="media-placeholder" aria-hidden="true" onDoubleClick={()=>onOpen?.()}>{url && <img className="synthetic-thumbnail" src={url} alt="" onError={() => setThumbnail(null)} />}<svg style={url ? {visibility: "hidden"} : undefined} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5">{item.kind === "video" ? <><rect x="8" y="11" width="32" height="26" rx="4" /><path d="m21 18 10 6-10 6z" /></> : <><rect x="7" y="10" width="34" height="28" rx="4" /><circle cx="17" cy="19" r="3" /><path d="m10 34 9-9 6 6 5-5 8 8" /></>}</svg><span className="media-kind">{url ? mediaLabel : mediaLabel}</span></div>
    <div className="media-card-body"><h3 title={item.representative_location?.relative_path ?? name}>{onSelect ? <button data-asset-id={item.asset_id} className="card-select" aria-pressed={selected} aria-label={`Detalhes de ${name}`} onClick={(event) => onSelect(event.currentTarget)} onDoubleClick={()=>onOpen?.()}>{name}</button> : name}</h3>{folder && <p className="card-metadata">{folder}</p>}<span className="sr-only">{mediaLabel}{url ? " — miniatura" : " — miniatura indisponível"}</span><AvailabilityIndicator availability={item.availability} />{onFavoriteChanged && <FavoriteButton assetId={item.asset_id} favorite={item.annotation.favorite} onChanged={onFavoriteChanged} />}{onOpen && <button className="open-image" onClick={()=>onOpen?.()}>Abrir imagem</button>}<p className="card-metadata">{item.media_type ?? "Formato desconhecido"}{item.annotation.favorite ? " · Favorito" : ""}{item.annotation.rating != null ? ` · ${item.annotation.rating}/5` : ""}</p></div>
  </article>;
}
