// @vitest-environment jsdom
import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {App} from "./App";
import {CaptureCalendar} from "./CaptureCalendar";
import {ImageViewer} from "./ImageViewer";
let host:HTMLDivElement;let root:Root;
beforeEach(()=>{Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});host=document.createElement("div");document.body.append(host);root=createRoot(host);window.photoManager={listGallery:vi.fn().mockResolvedValue({items:[],has_more:false,next_cursor:null}),retryGallery:vi.fn(),getCalendar:vi.fn().mockResolvedValue({period:null,buckets:[["2024",3]],undated:4,partial:0})};HTMLDialogElement.prototype.showModal=vi.fn();});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();delete window.photoManager;vi.useRealTimers();});
async function click(text:string){await act(async()=>[...host.querySelectorAll("button")].find(b=>b.textContent===text)!.click());}
it("drills through years, leap month, day and queries the entire catalog period",async()=>{
 window.photoManager!.getCalendar=vi.fn().mockImplementation((period)=>Promise.resolve({period,buckets:period===null?[["2024",3]]:period==="2024"?[["2024-02",3]]:[["2024-02-29",3]],undated:4,partial:0}));
 await act(async()=>root.render(<App/>));await click("Calendário");
 await click("20243 foto(s)");await click("Fevereiro3 foto(s)");
 expect(host.querySelectorAll(".calendar-days button")).toHaveLength(29);
 await act(async()=>host.querySelector<HTMLButtonElement>('[aria-label="2024-02-29: 3 foto(s)"]')!.click());
 expect(window.photoManager!.listGallery).toHaveBeenLastCalledWith({pageSize:24,capturePeriod:"2024-02-29"});
 expect(host.textContent).toContain("Captura: 2024-02-29");await click("Limpar período");
 expect(window.photoManager!.listGallery).toHaveBeenLastCalledWith({pageSize:24});
});
it("keeps undated and partial dates explicit and never uses creation time",async()=>{
 window.photoManager!.getCalendar=vi.fn().mockResolvedValue({period:"2024-02",buckets:[],undated:5,partial:2});const browse=vi.fn();
 await act(async()=>root.render(<CaptureCalendar period="2024-02" onPeriod={vi.fn()} onBrowse={browse}/>));
 expect(host.textContent).toContain("2 foto(s) com data parcial");expect(host.querySelectorAll(".calendar-days button:enabled")).toHaveLength(0);
 await click("Sem data de captura (5)");expect(browse).toHaveBeenCalledWith("undated");
});
it("discards late calendar responses and shows sanitized errors",async()=>{
 let finish!:(v:unknown)=>void;window.photoManager!.getCalendar=vi.fn().mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValueOnce({period:"2024",buckets:[["2024-02",1]],undated:0,partial:0});
 const props={onPeriod:vi.fn(),onBrowse:vi.fn()};await act(async()=>root.render(<CaptureCalendar period={null} {...props}/>));await act(async()=>root.render(<CaptureCalendar period="2024" {...props}/>));
 await act(async()=>finish({period:null,buckets:[["1999",99]],undated:99,partial:0}));expect(host.textContent).not.toContain("1999");expect(host.textContent).toContain("Fevereiro");
 window.photoManager!.getCalendar=vi.fn().mockRejectedValue(new Error("/private"));await act(async()=>root.render(<CaptureCalendar period="2025" {...props}/>));expect(host.querySelector('[role="alert"]')?.textContent).toContain("Não foi possível");expect(host.textContent).not.toContain("/private");
});
it("polls pending preview, displays bounded JPEG and closes without modifying media",async()=>{
 vi.useFakeTimers();window.photoManager!.getPreview=vi.fn().mockResolvedValueOnce({status:"pending"}).mockResolvedValue({media_type:"image/jpeg",base64:"/9j/AAAA"});const close=vi.fn();
 await act(async()=>root.render(<ImageViewer assetId="asset" onClose={close}/>));expect(host.textContent).toContain("Preparando prévia");await act(async()=>vi.advanceTimersByTimeAsync(150));
 expect(host.querySelector("img")?.getAttribute("src")).toBe("data:image/jpeg;base64,/9j/AAAA");Object.defineProperty(host.querySelector("img")!,"naturalWidth",{value:80});await act(async()=>host.querySelector("img")!.dispatchEvent(new Event("load")));await click("100%");expect(host.querySelector<HTMLImageElement>("img")?.style.width).toBe("80px");await click("Fechar imagem");expect(close).toHaveBeenCalledOnce();
});
it("rejects external preview URLs and stops polling after unmount",async()=>{
 window.photoManager!.getPreview=vi.fn().mockResolvedValue({media_type:"image/jpeg",base64:"https://invalid.test/private"});
 await act(async()=>root.render(<ImageViewer assetId="asset" onClose={vi.fn()}/>));expect(host.querySelector("img")).toBeNull();expect(host.textContent).toContain("Prévia indisponível");
});

it("never renders numeric short-circuit values in year or month headers",async()=>{
 const props={onPeriod:vi.fn(),onBrowse:vi.fn()};
 await act(async()=>root.render(<CaptureCalendar period={null} {...props}/>));
 expect(host.querySelector(".calendar-heading")!.textContent).not.toContain("NaN");
 expect(host.querySelector(".calendar-heading > div:last-child")!.textContent).toBe("Todos os anos");
 await act(async()=>root.render(<CaptureCalendar period="2024" {...props}/>));
 expect(host.querySelector(".calendar-heading > div:last-child")!.textContent).toBe("Todos os anos‹›Ver fotos do período");
});
