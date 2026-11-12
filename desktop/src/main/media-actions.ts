import {canonicalId,validPath} from "./library-preferences.js";
import type {LibraryController} from "./libraries.js";
export type MediaAction="view"|"properties"|"favorite"|"reveal"|"location"|"add-to-album";
export interface MediaMenuItem {label:string;action:MediaAction;enabled:boolean}
export class MediaActions {
 private busy=false;
 constructor(private readonly libraries:Pick<LibraryController,"current"|"query">,private readonly choose:(items:MediaMenuItem[])=>Promise<MediaAction|null>,private readonly reveal:(path:string)=>void,private readonly describe:(path:string)=>Promise<boolean>){}
 private check(session:unknown,asset:unknown){if(!canonicalId(session)||!canonicalId(asset)||this.libraries.current().session?.session_id!==session)throw new Error("stale_session");}
 async locate(session:unknown,asset:unknown,describe=false):Promise<{status:string}>{
  this.check(session,asset);
  const value=await this.libraries.query("asset.reveal",session,{asset_id:asset}) as {path?:unknown};
  this.check(session,asset);
  if(!validPath(value.path))throw new Error("unavailable");
  if(describe){const open=await this.describe(value.path);this.check(session,asset);if(!open)return {status:"cancelled"};return this.locate(session,asset);}
  this.reveal(value.path);return {status:"requested"};
 }
 async menu(session:unknown,asset:unknown){
  this.check(session,asset);if(this.busy)return null;this.busy=true;
  try{
   const details=await this.libraries.query("asset.details",session,{asset_id:asset}) as {availability:string;annotation:{favorite:boolean}|null;asset:{kind:string}};
   this.check(session,asset);
   const available=details.availability==="available";
   const action=await this.choose([
    {label:"Visualizar",action:"view",enabled:available&&details.asset.kind==="photo"},
    {label:"Abrir pasta que contém o arquivo",action:"reveal",enabled:available},
    {label:"Localização do arquivo…",action:"location",enabled:available},
    {label:details.annotation?.favorite?"Remover dos favoritos":"Adicionar aos favoritos",action:"favorite",enabled:true},
    {label:"Adicionar a álbum…",action:"add-to-album",enabled:true},
    {label:"Propriedades",action:"properties",enabled:true},
   ]);
   this.check(session,asset);
   if(action==="reveal"||action==="location"){await this.locate(session,asset,action==="location");return null;}
   return action;
  }finally{this.busy=false;}
 }
}
