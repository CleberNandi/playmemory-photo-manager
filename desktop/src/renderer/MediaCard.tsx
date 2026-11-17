import {mediaMenu} from "./media-menu";
import { useEffect, useState, type MouseEvent } from "react";
import { requestThumbnail } from "./thumbnails";
import type { GalleryItem } from "./types";
function getDisplayName(item: GalleryItem): string { return item.annotation.title?.trim() || item.representative_location?.relative_path.trim().split("/").pop() || "Sem título"; }
export function MediaCard({ item, selected = false, batchSelected = false, onSelect, onToggleBatch, onOpen, onFavoriteChanged, onAddToAlbum }: { item: GalleryItem; selected?: boolean; batchSelected?: boolean; onSelect?: (button: HTMLButtonElement, event?: MouseEvent<HTMLButtonElement>) => void; onToggleBatch?: (checked: boolean, shiftKey: boolean) => void; onOpen?: (rotation?:number) => void; onFavoriteChanged?: (favorite:boolean)=>void; onAddToAlbum?: ()=>void }) {
  const canOpen = item.kind === "photo" && item.availability === "available";
  const open = () => { if (canOpen) onOpen?.(); };
  const [menuError,setMenuError]=useState(false);
  const [thumbnail, setThumbnail] = useState<{id: string; availability:string; url: string} | null>(null);
  useEffect(() => requestThumbnail(item.asset_id, (url) => setThumbnail(url ? {id: item.asset_id, availability:item.availability, url} : null)), [item.asset_id,item.availability]);
  const url = thumbnail?.id === item.asset_id && thumbnail.availability === item.availability ? thumbnail.url : null;
  const name = getDisplayName(item); const mediaLabel = item.kind === "video" ? "Vídeo" : "Foto";
  const favoriteAction = onFavoriteChanged ? {current: item.annotation.favorite, onChanged: onFavoriteChanged} : undefined;
  return <article className={`media-card${batchSelected ? " is-batch-selected" : ""}`} role="listitem" onContextMenu={event=>{setMenuError(false);void mediaMenu(event,item.asset_id,onSelect,onOpen ? open : undefined,()=>setMenuError(true),onAddToAlbum,favoriteAction);}} onKeyDown={event=>{if(event.key==="ContextMenu"||(event.shiftKey&&event.key==="F10")){setMenuError(false);void mediaMenu(event,item.asset_id,onSelect,onOpen ? open : undefined,()=>setMenuError(true),onAddToAlbum,favoriteAction);}}}>
    {menuError&&<p role="alert">Não foi possível executar a ação. Confira se a imagem e a biblioteca continuam disponíveis.</p>}
    <div className="media-placeholder" aria-hidden="true" onDoubleClick={open}>{url && <img className="synthetic-thumbnail" src={url} alt="" onError={() => setThumbnail(null)} />}<svg style={url ? {visibility: "hidden"} : undefined} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5">{item.kind === "video" ? <><rect x="8" y="11" width="32" height="26" rx="4" /><path d="m21 18 10 6-10 6z" /></> : <><rect x="7" y="10" width="34" height="28" rx="4" /><circle cx="17" cy="19" r="3" /><path d="m10 34 9-9 6 6 5-5 8 8" /></>}</svg>{item.annotation.favorite && <span className="card-favorite-badge" title="Favorito">★</span>}<span className="media-kind">{mediaLabel}</span></div>
    <div className="media-card-body">
      <div className="media-card-header">
        {onToggleBatch && <input type="checkbox" className="batch-checkbox" aria-label={`Marcar ${name}`} checked={batchSelected} onChange={event => onToggleBatch(event.currentTarget.checked, (event.nativeEvent as globalThis.MouseEvent).shiftKey === true)} />}
        <h3 title={item.representative_location?.relative_path ?? name}>{onSelect ? <button data-asset-id={item.asset_id} className="card-select" aria-pressed={selected} aria-label={`Detalhes de ${name}`} onClick={(event) => onSelect(event.currentTarget, event)} onDoubleClick={open}>{name}</button> : name}</h3>
      </div>
      <span className="sr-only">{mediaLabel}{url ? " — miniatura" : " — miniatura indisponível"}{item.annotation.favorite ? " · Favorito" : ""}</span>
    </div>
  </article>;
}
