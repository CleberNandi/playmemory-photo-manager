// @vitest-environment jsdom
import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {App} from "./App";
import {CaptureCalendar} from "./CaptureCalendar";
import {ImageViewer,viewerGeometry} from "./ImageViewer";
let host:HTMLDivElement;let root:Root;
beforeEach(()=>{Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});host=document.createElement("div");document.body.append(host);root=createRoot(host);window.photoManager={listGallery:vi.fn().mockResolvedValue({items:[],has_more:false,next_cursor:null}),retryGallery:vi.fn(),getCalendar:vi.fn().mockResolvedValue({period:null,buckets:[["2024",3]],undated:4,partial:0})};HTMLDialogElement.prototype.showModal=vi.fn(function(this:HTMLDialogElement){this.setAttribute("open","");});});
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

it("rotates by quarter turns, resets and fits the rotated bounding box",async()=>{
 window.photoManager!.getPreview=vi.fn().mockResolvedValue({media_type:"image/jpeg",base64:"/9j/AAAA"});await act(async()=>root.render(<ImageViewer assetId="a" onClose={vi.fn()}/>));
 const image=host.querySelector("img")!;Object.defineProperties(image,{naturalWidth:{value:800},naturalHeight:{value:400}});await act(async()=>image.dispatchEvent(new Event("load")));
 await click("Girar à direita");expect(image.style.transform).toContain("rotate(90deg)");await click("Girar à esquerda");expect(image.style.transform).toContain("rotate(0deg)");await click("Girar à esquerda");expect(image.style.transform).toContain("rotate(270deg)");await click("Restaurar rotação");expect(image.style.transform).toContain("rotate(0deg)");
 expect(viewerGeometry(800,400,90,0,424,424)).toEqual({width:400,height:200,boxWidth:200,boxHeight:400});
 expect(viewerGeometry(800,400,90,100,424,424)).toEqual({width:800,height:400,boxWidth:400,boxHeight:800});
});
it("navigates with buttons and arrows without remounting the dialog or leaking Escape",async()=>{
 const previous=vi.fn(),next=vi.fn(),close=vi.fn();window.photoManager!.getPreview=vi.fn().mockResolvedValue({media_type:"image/jpeg",base64:"/9j/AAAA"});
 await act(async()=>root.render(<ImageViewer assetId="a" onClose={close} onPrevious={previous} onNext={next} name="A.jpg" position="2 de 3 imagens carregadas"/>));const dialog=host.querySelector("dialog")!;
 await click("Próxima");await act(async()=>document.body.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowLeft",bubbles:true})));expect(next).toHaveBeenCalledOnce();expect(previous).toHaveBeenCalledOnce();
 const escape=vi.fn();document.addEventListener("keydown",escape);await act(async()=>dialog.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true})));document.removeEventListener("keydown",escape);expect(escape).not.toHaveBeenCalled();
 await click("Girar à direita");await act(async()=>root.render(<ImageViewer assetId="b" onClose={close} name="B.jpg"/>));expect(host.querySelector("dialog")).toBe(dialog);expect(host.querySelector(".viewer-caption")!.textContent).toContain("B.jpg · 0°");expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalledTimes(1);
 await act(async()=>root.render(<ImageViewer assetId="a" onClose={close}/>));expect(host.querySelector(".viewer-caption")!.textContent).toContain("0°");
});
it("drops previous-asset previews while the next image is pending",async()=>{
 let finish!:(value:unknown)=>void;window.photoManager!.getPreview=vi.fn().mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValueOnce(null);
 await act(async()=>root.render(<ImageViewer assetId="old" onClose={vi.fn()}/>));await act(async()=>root.render(<ImageViewer assetId="new" onClose={vi.fn()}/>));await act(async()=>finish({media_type:"image/jpeg",base64:"/9j/AAAA"}));expect(host.querySelector("img")).toBeNull();expect(host.textContent).toContain("Prévia indisponível");
});
it("keeps the last navigated thumbnail selected after closing the viewer",async()=>{
 const make=(id:string)=>({asset_id:id,kind:"photo",media_type:"image/jpeg",created_at:"2026-01-01",availability:"available",annotation:{favorite:false,rating:null,title:null},representative_location:{relative_path:`${id}.jpg`,root_display_name:"Synthetic"}});
 window.photoManager!.listGallery=vi.fn().mockResolvedValue({items:[make("a"),make("b")],has_more:false,next_cursor:null});window.photoManager!.getPreview=vi.fn().mockResolvedValue({media_type:"image/jpeg",base64:"/9j/AAAA"});
 await act(async()=>root.render(<App/>));await click("Abrir imagem");expect(host.querySelector<HTMLButtonElement>('[aria-label="Imagem anterior"]')!.disabled).toBe(true);await click("Próxima");expect(host.querySelector(".viewer-caption")!.textContent).toContain("b.jpg · 2 de 2");expect(host.querySelector<HTMLButtonElement>('[aria-label="Próxima imagem"]')!.disabled).toBe(true);await click("Fechar imagem");expect(host.querySelector('[data-asset-id="b"]')?.getAttribute("aria-pressed")).toBe("true");expect(document.activeElement).toBe(host.querySelector('[data-asset-id="b"]'));
});

it("asks before leaving an unsaved rotation and offers discard or continuing",async()=>{
 window.photoManager!.getPreview=vi.fn().mockResolvedValue({media_type:"image/jpeg",base64:"/9j/AAAA"});const close=vi.fn();await act(async()=>root.render(<ImageViewer assetId="a" onClose={close}/>));await click("Girar à direita");await click("Fechar imagem");expect(close).not.toHaveBeenCalled();expect(host.querySelector('[role="alertdialog"]')).not.toBeNull();await click("Continuar editando");expect(host.querySelector('[role="alertdialog"]')).toBeNull();await click("Fechar imagem");await click("Descartar rotação");expect(close).toHaveBeenCalledOnce();
});
it("saves full-resolution rotation through scoped commands and refreshes the preview",async()=>{
 vi.useFakeTimers();window.photoManager!.getPreview=vi.fn().mockResolvedValue({media_type:"image/jpeg",base64:"/9j/AAAA"});window.photoManager!.saveRotation=vi.fn().mockResolvedValue({job_id:"job",asset_id:"a",state:"running",result_asset_id:null,error:null});window.photoManager!.getImageSaveStatus=vi.fn().mockResolvedValue({job_id:"job",asset_id:"a",state:"completed",result_asset_id:"copy",error:null});const saved=vi.fn();await act(async()=>root.render(<ImageViewer assetId="a" onClose={vi.fn()} onSaved={saved}/>));await click("Girar à direita");await click("Salvar como cópia");expect(window.photoManager!.saveRotation).toHaveBeenCalledWith("a",90,"copy");await act(async()=>vi.advanceTimersByTimeAsync(250));expect(saved).toHaveBeenCalledWith("copy","copy");expect(host.textContent).toContain("Cópia salva");expect(host.querySelector(".viewer-caption")?.textContent).not.toContain("90°");expect(window.photoManager!.getPreview).toHaveBeenCalledTimes(2);
});
it("cancelled saving preserves edits and an unknown outcome blocks further saves",async()=>{
 window.photoManager!.getPreview=vi.fn().mockResolvedValue({media_type:"image/jpeg",base64:"/9j/AAAA"});window.photoManager!.saveRotation=vi.fn().mockResolvedValueOnce({job_id:"job",asset_id:"a",state:"cancelled",result_asset_id:null,error:null}).mockResolvedValueOnce({job_id:"job2",asset_id:"a",state:"outcome_unknown",result_asset_id:null,error:"outcome_unknown"});await act(async()=>root.render(<ImageViewer assetId="a" onClose={vi.fn()}/>));await click("Girar à direita");await click("Salvar alterações");expect(host.textContent).toContain("90°");await click("Salvar alterações");expect([...host.querySelectorAll("button")].find(button=>button.textContent==="Salvar alterações")!.disabled).toBe(true);expect(host.textContent).toContain("não haverá repetição automática");
});
