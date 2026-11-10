// @vitest-environment jsdom
import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {FavoriteButton} from "./FavoriteButton";
import {App} from "./App";
import type {GalleryItem} from "./types";
let root:Root;let host:HTMLDivElement;
beforeEach(()=>{Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});host=document.createElement("div");document.body.append(host);root=createRoot(host);window.photoManager={listGallery:vi.fn(),retryGallery:vi.fn(),setFavorite:vi.fn().mockResolvedValue({asset_id:"asset",favorite:true})};});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();delete window.photoManager;vi.useRealTimers();});
it("sends an explicit boolean once and publishes only acknowledged state",async()=>{
 let finish!:(v:{asset_id:string;favorite:boolean})=>void;window.photoManager!.setFavorite=vi.fn().mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));const changed=vi.fn();
 await act(async()=>root.render(<FavoriteButton assetId="asset" favorite={false} onChanged={changed}/>));
 await act(async()=>{host.querySelector("button")!.click();host.querySelector("button")!.click();});
 expect(window.photoManager!.setFavorite).toHaveBeenCalledExactlyOnceWith("asset",true);expect(host.querySelector("button")!.disabled).toBe(true);expect(changed).not.toHaveBeenCalled();
 await act(async()=>finish({asset_id:"asset",favorite:true}));expect(changed).toHaveBeenCalledExactlyOnceWith(true);
});
it("does not retry lost acknowledgements or leak error details",async()=>{
 vi.useFakeTimers();window.photoManager!.setFavorite=vi.fn().mockRejectedValue(new Error("/private/path"));const changed=vi.fn();
 await act(async()=>root.render(<FavoriteButton assetId="asset" favorite={false} onChanged={changed}/>));await act(async()=>host.querySelector("button")!.click());await act(async()=>vi.advanceTimersByTimeAsync(10000));
 expect(window.photoManager!.setFavorite).toHaveBeenCalledOnce();expect(changed).not.toHaveBeenCalled();expect(host.querySelector("[role=alert]")?.textContent).toContain("Reabra a biblioteca");expect(host.textContent).not.toContain("/private");expect(host.querySelector("button")!.getAttribute("aria-pressed")).toBe("false");
});
it("ignores a late response after closing the old session",async()=>{
 let finish!:(v:unknown)=>void;window.photoManager!.setFavorite=vi.fn().mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));const changed=vi.fn();
 await act(async()=>root.render(<FavoriteButton assetId="old" favorite={false} onChanged={changed}/>));await act(async()=>host.querySelector("button")!.click());await act(async()=>root.render(<p>Outra biblioteca</p>));await act(async()=>finish({asset_id:"old",favorite:true}));expect(changed).not.toHaveBeenCalled();
});
it("rejects an acknowledgement from a different asset",async()=>{
 window.photoManager!.setFavorite=vi.fn().mockResolvedValue({asset_id:"other",favorite:true});const changed=vi.fn();
 await act(async()=>root.render(<FavoriteButton assetId="asset" favorite={false} onChanged={changed}/>));await act(async()=>host.querySelector("button")!.click());expect(changed).not.toHaveBeenCalled();expect(host.querySelector("[role=alert]")).not.toBeNull();
});
it("marks cards, queries beyond the first page and removes unfavorited cards",async()=>{
 const item=(id:string,favorite:boolean):GalleryItem=>({asset_id:id,kind:"photo",created_at:"2026-01-01",media_type:"image/jpeg",availability:"available",annotation:{title:id,favorite,rating:null},representative_location:null});
 let first=false;
 Object.assign(window.photoManager!,{
  getLibraryState:vi.fn().mockResolvedValue({state:"active",session:{session_id:"session",display_name:"Synthetic"},cataloging_enabled:false,reopen:false}),
  listGallery:vi.fn().mockImplementation((params)=>Promise.resolve({items:params?.favoritesOnly?[...(first?[item("first",true)]:[]),item("beyond-first-page",true)]:[item("first",first)],has_more:false,next_cursor:null})),
  setFavorite:vi.fn().mockImplementation((asset_id,favorite)=>{if(asset_id==="first")first=favorite;return Promise.resolve({asset_id,favorite});}),
 });
 await act(async()=>root.render(<App/>));await act(async()=>host.querySelector<HTMLButtonElement>(".favorite-toggle")!.click());expect(host.querySelector(".favorite-toggle")?.getAttribute("aria-pressed")).toBe("true");
 await act(async()=>[...host.querySelectorAll("button")].find(b=>b.textContent==="☆ Favoritos")!.click());expect(window.photoManager!.listGallery).toHaveBeenLastCalledWith({pageSize:24,favoritesOnly:true});expect(host.querySelectorAll(".media-card")).toHaveLength(2);expect(host.textContent).toContain("beyond-first-page");
 await act(async()=>host.querySelector<HTMLButtonElement>(".favorite-toggle")!.click());expect(host.querySelectorAll(".media-card")).toHaveLength(1);expect(host.querySelector(".media-card")?.textContent).toContain("beyond-first-page");expect(window.photoManager!.setFavorite).toHaveBeenLastCalledWith("first",false);
});
