// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CatalogingReview, type CandidatePage } from "./CatalogingReview";
let root: Root; let host: HTMLDivElement;
const selected = (id: string, selectable = true) => ({candidate_id:id, relative_path:`nested/${id}.jpg`, state:"eligible", reason:"eligible_jpeg", profile:"jpeg_structural_v1", decoding:"not_checked", selectable});
const page: CandidatePage = {proposal_id:"proposal", next_cursor:null, items:[selected("a"), selected("known",false), {...selected("excluded",false),state:"excluded",reason:"unsupported_extension"}]};
const applied = vi.fn(); const locked = vi.fn();
const command = (state = "running") => ({command_id:"command", state, result:state === "completed" ? {status:"applied",diagnostic:null,items:[{candidate_id:"a",disposition:"created",asset_id:"asset",location_id:"location"}]} : null});
beforeEach(() => {
  vi.useFakeTimers(); applied.mockClear(); locked.mockClear();
  Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true}); host=document.createElement("div");document.body.append(host);root=createRoot(host);
  window.photoManager={listGallery:vi.fn(),retryGallery:vi.fn(),applyCataloging:vi.fn().mockResolvedValue(command()),getCatalogingApplicationStatus:vi.fn().mockResolvedValue(command("completed"))};
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();delete window.photoManager;vi.useRealTimers();});
async function mount(value = page){await act(async()=>root.render(<CatalogingReview sessionId="session" proposalId="proposal" page={value} onApplied={applied} onLockChange={locked}/>));}
async function click(text:string){await act(async()=>[...host.querySelectorAll("button")].find(b=>b.textContent===text)!.click());}
it("requires explicit eligible selection, polls once to completion and refreshes once",async()=>{
 await mount(); expect([...host.querySelectorAll("button")].find(b=>b.textContent==="Catalogar selecionados")!.disabled).toBe(true);
 expect(host.querySelector<HTMLInputElement>('[aria-label="Selecionar nested/known.jpg"]')!.disabled).toBe(true);
 expect(host.querySelector<HTMLInputElement>('[aria-label="Selecionar nested/excluded.jpg"]')!.disabled).toBe(true);
 await click("Selecionar elegíveis desta página");
 expect(window.photoManager!.applyCataloging).not.toHaveBeenCalled();
 await click("Catalogar selecionados");
 expect(window.photoManager!.applyCataloging).toHaveBeenCalledWith("session","proposal",["a"]);
 expect(locked).toHaveBeenLastCalledWith(true);
 await act(async()=>vi.advanceTimersByTimeAsync(250));
 expect(host.textContent).toContain("Catalogação concluída"); expect(applied).toHaveBeenCalledOnce();
 await act(async()=>vi.advanceTimersByTimeAsync(1500));
 expect(window.photoManager!.getCatalogingApplicationStatus).toHaveBeenCalledOnce();expect(locked).toHaveBeenLastCalledWith(false);
});
it("preserves choices across pages and limits selection to 100",async()=>{
 await mount();await click("Selecionar elegíveis desta página");
 await mount({...page,items:Array.from({length:101},(_,i)=>selected(`b${i}`))});
 await click("Selecionar elegíveis desta página");expect(host.textContent).toContain("100 selecionado(s)");
 await click("Catalogar selecionados");
 const request=vi.mocked(window.photoManager!.applyCataloging!).mock.calls[0][2];expect(request).toHaveLength(100);expect(request).toContain("a");
});
it("native cancellation preserves selection and permits a new explicit confirmation",async()=>{
 window.photoManager!.applyCataloging=vi.fn().mockResolvedValue({cancelled:true});
 await mount();await click("Selecionar elegíveis desta página");await click("Catalogar selecionados");
 expect(host.textContent).toContain("1 selecionado(s)");expect(host.textContent).not.toContain("Resultado incerto");
 await click("Catalogar selecionados");expect(window.photoManager!.applyCataloging).toHaveBeenCalledTimes(2);expect(applied).not.toHaveBeenCalled();
});
it("lost response locks the proposal without automatic mutation retry",async()=>{
 window.photoManager!.applyCataloging=vi.fn().mockRejectedValue(new Error("private path"));
 await mount();await click("Selecionar elegíveis desta página");await click("Catalogar selecionados");
 expect(host.textContent).toContain("Resultado incerto");expect(host.textContent).not.toContain("private path");
 await act(async()=>vi.advanceTimersByTimeAsync(3000));expect(window.photoManager!.applyCataloging).toHaveBeenCalledOnce();expect(locked).toHaveBeenLastCalledWith(true);
});
it("late admission after unmount never refreshes the old library",async()=>{
 let finish!:(value:unknown)=>void;
 window.photoManager!.applyCataloging=vi.fn().mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 await mount();await click("Selecionar elegíveis desta página");await click("Catalogar selecionados");
 await act(async()=>root.render(<p>Outra sessão</p>));await act(async()=>finish(command("completed")));
 expect(applied).not.toHaveBeenCalled();expect(window.photoManager!.getCatalogingApplicationStatus).not.toHaveBeenCalled();
});
it("a status from another command becomes unknown and stops polling",async()=>{
 window.photoManager!.getCatalogingApplicationStatus=vi.fn().mockResolvedValue({...command("completed"),command_id:"other"});
 await mount();await click("Selecionar elegíveis desta página");await click("Catalogar selecionados");
 await act(async()=>vi.advanceTimersByTimeAsync(1250));expect(host.textContent).toContain("Resultado incerto");expect(applied).not.toHaveBeenCalled();expect(window.photoManager!.getCatalogingApplicationStatus).toHaveBeenCalledOnce();
});
