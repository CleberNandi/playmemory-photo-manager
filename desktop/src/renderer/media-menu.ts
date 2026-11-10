import type {KeyboardEvent,MouseEvent} from "react";
export async function mediaMenu(event:MouseEvent<HTMLElement>|KeyboardEvent<HTMLElement>,assetId:string,onSelect?:(button:HTMLButtonElement)=>void,onOpen?:(rotation?:number)=>void,onError?:()=>void){
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
  else if(action==="favorite")host.querySelector<HTMLButtonElement>(".favorite-toggle")?.click();
  if(action!=="view"&&action!=="properties")button?.focus({preventScroll:true});
 }catch{if(host.isConnected)onError?.();}
}
