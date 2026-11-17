import type {KeyboardEvent,MouseEvent} from "react";
export async function mediaMenu(event:MouseEvent<HTMLElement>|KeyboardEvent<HTMLElement>,assetId:string,onSelect?:(button:HTMLButtonElement)=>void,onOpen?:(rotation?:number)=>void,onError?:()=>void,onAddToAlbum?:()=>void,favorite?:{current:boolean;onChanged:(value:boolean)=>void}){
 if(!window.photoManager?.showMediaMenu)return;
 event.preventDefault();event.stopPropagation();
 const host=event.currentTarget;
 const button=host.querySelector<HTMLButtonElement>("[data-asset-id]");
 // Keep the same selection and return focus when the native popup is dismissed.
 if(button)onSelect?.(button);
 try{
  const action=await window.photoManager.showMediaMenu(assetId);
  if(!host.isConnected)return;
  if(action==="view")onOpen?.();
  else if(action==="properties"){if(button)onSelect?.(button);}
  else if(action==="add-to-album"){onAddToAlbum?.();return;}
  else if(action==="favorite"){
   const toggle=host.querySelector<HTMLButtonElement>(".favorite-toggle");
   if(toggle)toggle.click();
   else if(favorite&&window.photoManager?.setFavorite){
    const ack=await window.photoManager.setFavorite(assetId,!favorite.current);
    if(host.isConnected&&ack.asset_id===assetId)favorite.onChanged(ack.favorite);
   }
  }
  if(action!=="view"&&action!=="properties")button?.focus({preventScroll:true});
 }catch{if(host.isConnected)onError?.();}
}
