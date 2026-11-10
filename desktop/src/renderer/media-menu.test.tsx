// @vitest-environment jsdom
import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {MediaCard} from "./MediaCard";
vi.mock("./thumbnails",()=>({requestThumbnail:()=>()=>{}}));
let host:HTMLDivElement,root:Root;
const item={asset_id:"asset",kind:"photo" as const,media_type:"image/jpeg",created_at:"2026-01-01",availability:"available" as const,annotation:{rating:null,favorite:false,title:null},representative_location:{relative_path:"nested/synthetic.jpg",root_display_name:"Synthetic"}};
beforeEach(()=>{Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});host=document.createElement("div");document.body.append(host);root=createRoot(host);window.photoManager={listGallery:vi.fn(),retryGallery:vi.fn(),showMediaMenu:vi.fn().mockResolvedValue(null),setFavorite:vi.fn().mockResolvedValue({asset_id:"asset",favorite:true})};});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();delete window.photoManager;});
it("right click selects the target and cancellation keeps focus without opening a viewer",async()=>{
 const select=vi.fn(),open=vi.fn();await act(async()=>root.render(<MediaCard item={item} onSelect={select} onOpen={open}/>));await act(async()=>{host.querySelector("article")!.dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,cancelable:true}));});expect(window.photoManager!.showMediaMenu).toHaveBeenCalledWith("asset");expect(select).toHaveBeenCalledWith(host.querySelector(".card-select"));expect(open).not.toHaveBeenCalled();expect(document.activeElement).toBe(host.querySelector(".card-select"));
});
it("Shift F10 supports viewing and the favorite action reuses the explicit save command",async()=>{
 const open=vi.fn(),changed=vi.fn();window.photoManager!.showMediaMenu=vi.fn().mockResolvedValueOnce("view").mockResolvedValueOnce("favorite");await act(async()=>root.render(<MediaCard item={item} onOpen={open} onSelect={vi.fn()} onFavoriteChanged={changed}/>));
 await act(async()=>{host.querySelector(".card-select")!.dispatchEvent(new KeyboardEvent("keydown",{key:"F10",shiftKey:true,bubbles:true,cancelable:true}));});expect(open).toHaveBeenCalledOnce();
 await act(async()=>{host.querySelector("article")!.dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,cancelable:true}));});expect(window.photoManager!.setFavorite).toHaveBeenCalledWith("asset",true);expect(changed).toHaveBeenCalledWith(true);
});
it("drops late menu actions after unmount and sanitizes failures",async()=>{
 let finish!:(action:"view")=>void;window.photoManager!.showMediaMenu=vi.fn().mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));const open=vi.fn();await act(async()=>root.render(<MediaCard item={item} onOpen={open}/>));await act(async()=>{host.querySelector("article")!.dispatchEvent(new MouseEvent("contextmenu",{bubbles:true}));});await act(async()=>root.render(<div/>));await act(async()=>finish("view"));expect(open).not.toHaveBeenCalled();
 window.photoManager!.showMediaMenu=vi.fn().mockRejectedValue(new Error("private path"));await act(async()=>root.render(<MediaCard item={item}/>));await act(async()=>{host.querySelector("article")!.dispatchEvent(new MouseEvent("contextmenu",{bubbles:true}));});expect(host.querySelector('[role="alert"]')).not.toBeNull();expect(host.textContent).not.toContain("private path");
});
