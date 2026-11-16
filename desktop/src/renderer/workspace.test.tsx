// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import type { AssetDetails, GalleryItem } from "./types";
let host: HTMLDivElement; let root: Root;
const item = (id: string, folder: string, favorite: boolean): GalleryItem => ({asset_id: id, kind: "photo", media_type: "image/jpeg", created_at: "2026-01-01", availability: "available", annotation: {title: id, favorite, rating: null}, representative_location: {relative_path: `${id}.jpg`, root_display_name: folder}});
beforeEach(() => {
  Object.assign(globalThis, {IS_REACT_ACT_ENVIRONMENT: true});
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
  window.photoManager = {listGallery: vi.fn().mockResolvedValue({items: [item("first", "Natureza", true), item("second", "Viagens", false)], next_cursor: "opaque", has_more: true}), retryGallery: vi.fn()};
});
afterEach(async () => {await act(async () => root.unmount()); host.remove(); delete window.photoManager; vi.useRealTimers();});
async function click(text: string) {await act(async () => {[...host.querySelectorAll("button")].find((b) => b.textContent === text)!.click();});}
it("filters loaded roots locally and queries favorites across the catalog", async () => {
  await act(async () => root.render(<App />));
  await click("Pastas"); await click("Viagens"); expect(host.querySelectorAll(".media-card")).toHaveLength(1);
  expect(host.querySelector(".media-card")?.textContent).toContain("second");
  await click("☆ Favoritos"); expect(host.querySelector(".media-card")?.textContent).toContain("first");
  await act(async () => host.querySelector<HTMLButtonElement>('.view-toolbar button:nth-of-type(2)')!.click());
  expect(host.querySelectorAll(".gallery-table tbody tr")).toHaveLength(1);
  expect(window.photoManager!.listGallery).toHaveBeenCalledTimes(2);
  expect(window.photoManager!.listGallery).toHaveBeenLastCalledWith({pageSize:24,favoritesOnly:true});
  expect(host.querySelector(".pagination button")?.textContent).toBe("Carregar mais");
});
it("clears selection when filtering and supports keyboard-compatible pane ranges", async () => {
  await act(async () => root.render(<App />));
  await act(async () => host.querySelector<HTMLButtonElement>(".card-select")!.click());
  expect(host.querySelector(".asset-details")).not.toBeNull();
  await act(async () => {
    const input = host.querySelector<HTMLInputElement>('input[type="search"]')!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "no match");
    input.dispatchEvent(new Event("input", {bubbles: true}));
  });
  vi.mocked(window.photoManager!.listGallery).mockResolvedValueOnce({items: [], next_cursor: null, has_more: false});
  await click("Buscar");
  expect(window.photoManager!.listGallery).toHaveBeenLastCalledWith({pageSize:24,filters:{keyword:"no match"}});
  expect(host.querySelector(".asset-details")).toBeNull();
  expect(host.querySelectorAll(".media-card")).toHaveLength(0);
  expect(host.textContent).toContain("Nenhuma foto corresponde aos filtros");
  await act(async () => {
    const input = host.querySelector<HTMLInputElement>('[aria-label="Largura da navegação"]')!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "270");
    input.dispatchEvent(new Event("change", {bubbles: true}));
  });
  expect(host.querySelector<HTMLElement>(".app-shell")!.style.getPropertyValue("--left-width")).toBe("270px");
  await click("Propriedades"); expect(host.querySelector(".properties-empty")).toBeNull();
});
it("does not substitute catalog creation dates for capture dates", async () => {
  await act(async () => root.render(<App />));
  for (const name of ["Calendário", "Ano", "Mês", "Dia"]) expect([...host.querySelectorAll("button")].find((b) => b.textContent === name)!.disabled).toBe(true);
  expect(host.querySelector<HTMLButtonElement>(".sidebar-footer button")!.disabled).toBe(true);
});
it("keeps polling when preparation is collapsed and stops after session close", async () => {
  vi.useFakeTimers();
  const job = {session_id: "A", operation_id: "op", revision: 1, state: "running", phase: "scanning", observed_count: 0, verified_count: 0, excluded_count: 0, total: null, proposal_id: null};
  Object.assign(window.photoManager!, {
    getLibraryState: vi.fn().mockResolvedValue({state: "active", session: {session_id: "A", display_name: "lab"}, cataloging_enabled: true, reopen: false}),
    chooseMediaRoot: vi.fn().mockResolvedValue({root_grant_id: "grant"}), prepareCataloging: vi.fn().mockResolvedValue(job), getPreparationStatus: vi.fn().mockResolvedValue(job),
    closeLibrary: vi.fn().mockResolvedValue({state: "no_library", session: null, reopen: false}),
  });
  await act(async () => root.render(<App />));
  await click("+ Adicionar pastas"); await click("Selecionar pasta"); await click("Preparar proposta");
  await click("Recolher preparação"); await act(async () => vi.advanceTimersByTimeAsync(250));
  expect(window.photoManager!.getPreparationStatus).toHaveBeenCalledOnce();
  await click("+ Adicionar pastas"); expect(window.photoManager!.prepareCataloging).toHaveBeenCalledOnce();
  await click("Fechar biblioteca"); await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(window.photoManager!.getPreparationStatus).toHaveBeenCalledOnce();
});

it("restores focus to the selection after switching from thumbnails to table", async () => {
  await act(async () => root.render(<App />));
  await act(async () => host.querySelector<HTMLButtonElement>(".card-select")!.click());
  await act(async () => host.querySelector<HTMLButtonElement>(".view-toolbar button:nth-of-type(2)")!.click());
  await click("Fechar detalhes");
  expect(document.activeElement).toBe(host.querySelector(".gallery-table [data-asset-id=first]"));
});

it("refreshes gallery after cataloging and discards a delayed pre-commit page", async () => {
  let oldPage!: (page: unknown) => void;
  const list = vi.fn().mockResolvedValueOnce({items:[item("before","Natureza",false)],next_cursor:"old",has_more:true})
    .mockImplementationOnce(()=>new Promise(resolve=>{oldPage=resolve;}))
    .mockResolvedValueOnce({items:[item("created","Natureza",false)],next_cursor:null,has_more:false});
  Object.assign(window.photoManager!, {
    listGallery:list,
    getLibraryState:vi.fn().mockResolvedValue({state:"active",session:{session_id:"A",display_name:"lab"},cataloging_enabled:true,reopen:false}),
    chooseMediaRoot:vi.fn().mockResolvedValue({root_grant_id:"grant"}),
    prepareCataloging:vi.fn().mockResolvedValue({session_id:"A",operation_id:"op",revision:1,state:"completed",phase:null,observed_count:1,verified_count:1,excluded_count:0,total:null,proposal_id:"proposal",terminal_reason:null}),
    listCatalogingCandidates:vi.fn().mockResolvedValue({proposal_id:"proposal",next_cursor:null,items:[{candidate_id:"candidate",relative_path:"new.jpg",state:"eligible",reason:"eligible_jpeg",profile:"jpeg_structural_v1",decoding:"not_checked",selectable:true}]}),
    applyCataloging:vi.fn().mockResolvedValue({command_id:"command",state:"completed",result:{status:"applied",diagnostic:null,items:[{candidate_id:"candidate",disposition:"created",asset_id:"created",location_id:"location"}]}}),
    getCatalogingApplicationStatus:vi.fn(),
  });
  await act(async()=>root.render(<App />));
  await click("Carregar mais");await click("+ Adicionar pastas");await click("Selecionar pasta");await click("Preparar proposta");await click("Ver proposta");
  await click("Selecionar elegíveis desta página");await click("Catalogar selecionados");
  expect(host.querySelectorAll(".media-card")).toHaveLength(1);
  expect(host.querySelector(".media-card")?.textContent).toContain("created");
  await act(async()=>oldPage({items:[item("stale","Natureza",false)],next_cursor:null,has_more:false}));
  expect(host.querySelectorAll(".media-card")).toHaveLength(1);expect(host.querySelector(".media-card")?.textContent).not.toContain("stale");
});
it("reloads new catalog additions without clearing the selected image",async()=>{
 let changed!:()=>void;window.photoManager!.onGalleryChanged=(listener)=>{changed=listener;return ()=>{};};
 await act(async()=>root.render(<App/>));await act(async()=>host.querySelector<HTMLButtonElement>('[data-asset-id="first"]')!.click());
 window.photoManager!.listGallery=vi.fn().mockResolvedValue({items:[item("first","Natureza",true),item("second","Viagens",false),item("new","Natureza",false)],next_cursor:null,has_more:false});
 await act(async()=>changed());expect(host.querySelectorAll(".media-card")).toHaveLength(3);expect(host.querySelector('[data-asset-id="first"]')?.getAttribute("aria-pressed")).toBe("true");
});

it("refreshes retained thumbnails and selected properties after a folder update",async()=>{
 let changed!:()=>void;
 window.photoManager!.onGalleryChanged=listener=>{changed=listener;return ()=>{};};
 const png={media_type:"image/png",width:256,height:160,base64:"iVBORw0KGgo="};
 window.photoManager!.getThumbnail=vi.fn().mockImplementation(()=>Promise.resolve(png));
 window.photoManager!.getAssetDetails=vi.fn().mockResolvedValue({status:"not_found"});
 await act(async()=>root.render(<App/>));
 await act(async()=>host.querySelector<HTMLButtonElement>('[data-asset-id="first"]')!.click());
 const image=()=>host.querySelector('[data-asset-id="first"]')!.closest(".media-card")!.querySelector("img");
 expect(image()?.getAttribute("src")).toBe("data:image/png;base64,iVBORw0KGgo=");
 expect(window.photoManager!.getAssetDetails).toHaveBeenCalledTimes(1);
 png.base64="iVBORw0KGgoA";
 await act(async()=>changed());
 expect(image()?.getAttribute("src")).toBe("data:image/png;base64,iVBORw0KGgoA");
 expect(window.photoManager!.getAssetDetails).toHaveBeenCalledTimes(2);
 expect(host.querySelector('[data-asset-id="first"]')?.getAttribute("aria-pressed")).toBe("true");
});

it("clears the selected properties only after confirming the removed item is missing",async()=>{
 let changed!:()=>void;
 window.photoManager!.onGalleryChanged=listener=>{changed=listener;return ()=>{};};
 const details:AssetDetails={
  asset:{id:"first",kind:"photo",media_type:"image/jpeg",byte_size:null,sha256:null,hash_state:"absent",status:"active",created_at:""},
  capture:null,annotation:null,tags:[],metadata:[],metadata_state:"extracted",availability:"available",locations_truncated:false,
  locations:[{id:"location",library_root_id:"root",root_display_name:"Synthetic",relative_path:"teste/first.jpg",entry_type:"file",availability:"present",root_availability:"available",observed_byte_size:null,observed_mtime_ns:null,last_seen_at:null}],
 };
 window.photoManager!.getAssetDetails=vi.fn().mockImplementation(()=>Promise.resolve({status:"ready",details}));
 await act(async()=>root.render(<App/>));
 await act(async()=>host.querySelector<HTMLButtonElement>('[data-asset-id="first"]')!.click());
 expect(host.querySelector(".asset-details")).not.toBeNull();
 details.availability="unavailable";details.locations[0].availability="missing";
 window.photoManager!.listGallery=vi.fn().mockResolvedValue({items:[item("second","Viagens",false)],has_more:false,next_cursor:null});
 await act(async()=>changed());
 expect(host.querySelector('[data-asset-id="first"]')).toBeNull();
 expect(host.querySelector('[data-asset-id="second"]')).not.toBeNull();
 expect(host.querySelector(".asset-details")).toBeNull();
});

it("selects a label beyond the initial filter options and keeps its name visible", async () => {
  const facets = {tags:[{id:"initial",name:"Primeiro"}], types:[], cameras:[], lenses:[], more:["tags" as const]};
  const page = {items:[], next_cursor:null, has_more:false, facets};
  const list = vi.fn().mockResolvedValue(page);
  const options = vi.fn().mockRejectedValueOnce(new Error("temporary"))
    .mockResolvedValueOnce({options:[{id:"later",name:"Viagem"}], next_offset:null});
  Object.assign(window.photoManager!, {listGallery:list, listFilterOptions:options});
  await act(async()=>root.render(<App/>));
  const select = host.querySelector<HTMLSelectElement>('[aria-label="Rótulos"]')!;
  await act(async()=>{
    select.value = "Mais opções…";
    select.dispatchEvent(new Event("change",{bubbles:true}));
  });
  const input = host.querySelector<HTMLInputElement>('[aria-label="Buscar opções de Rótulos"]')!;
  await act(async()=>{
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")!.set!.call(input,"viag");
    input.dispatchEvent(new Event("input",{bubbles:true}));
  });
  await click("Buscar opções");
  expect(host.querySelector(".facet-options [role=alert]")?.textContent).toContain("Falha");
  await click("Buscar opções");
  expect(options).toHaveBeenLastCalledWith("tags","viag",0);
  await click("Viagem");
  expect(list).toHaveBeenLastCalledWith({pageSize:24,filters:{tag_id:"later"}});
  expect(select.selectedOptions[0].textContent).toBe("Viagem");
  expect(host.querySelector(".facet-options")).toBeNull();
  expect(document.activeElement).toBe(select);
});

it("filters by creation and modification dates and shows top toast balloons on album actions", async () => {
  const album = {id: "alb-1", name: "Favoritas"};
  const details: AssetDetails = {
    asset: {id: "first", kind: "photo", media_type: "image/jpeg", byte_size: null, sha256: null, hash_state: "absent", status: "active", created_at: ""},
    capture: null, annotation: null, tags: [], albums: [], metadata: [], metadata_state: "extracted", availability: "available", locations_truncated: false, locations: [],
  };
  Object.assign(window.photoManager!, {
    getLibraryState: vi.fn().mockResolvedValue({state: "active", session: {session_id: "A", library_handle: "h", generation: 1, display_name: "lab"}, reopen: false}),
    getAssetDetails: vi.fn().mockImplementation(async () => ({status: "ready", details: {...details, albums: [...(details.albums ?? [])]}})),
    listAlbums: vi.fn().mockResolvedValue({albums: [album], next_offset: null}),
    createAlbum: vi.fn().mockResolvedValue(album),
    changeAlbumMembership: vi.fn().mockImplementation(async () => {
      details.albums = [album];
      return {changed: true};
    }),
  });
  await act(async () => root.render(<App />));
  const createdInput = host.querySelector<HTMLInputElement>('[aria-label="Data de criação"]')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(createdInput, "2026-10-15");
    createdInput.dispatchEvent(new Event("change", {bubbles: true}));
  });
  expect(window.photoManager!.listGallery).toHaveBeenLastCalledWith({pageSize: 24, filters: {created_date: "2026-10-15"}});
  const modifiedInput = host.querySelector<HTMLInputElement>('[aria-label="Data de modificação"]')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(modifiedInput, "2026-11-13");
    modifiedInput.dispatchEvent(new Event("change", {bubbles: true}));
  });
  expect(window.photoManager!.listGallery).toHaveBeenLastCalledWith({pageSize: 24, filters: {created_date: "2026-10-15", modified_date: "2026-11-13"}});

  await act(async () => host.querySelector<HTMLButtonElement>('[data-asset-id="first"]')!.click());
  await click("Adicionar a álbum…");
  await click("Favoritas");
  const toast = host.querySelector(".action-toast");
  expect(toast?.textContent).toContain("Item adicionado a “Favoritas”.");
  expect(host.querySelector(".asset-details")?.textContent).toContain("Favoritas");
  await act(async () => host.querySelector<HTMLButtonElement>(".toast-dismiss")!.click());
  expect(host.querySelector(".action-toast")).toBeNull();
});

it("selects multiple photos in batch, favorites them, and adds them to an album", async () => {
  const album = {id: "alb-batch", name: "Lote"};
  const setFavorite = vi.fn().mockImplementation(async (asset_id: string, favorite: boolean) => ({asset_id, favorite}));
  const changeAlbumMembership = vi.fn().mockResolvedValue({changed: true});
  Object.assign(window.photoManager!, {
    getLibraryState: vi.fn().mockResolvedValue({state: "active", session: {session_id: "A", library_handle: "h", generation: 1, display_name: "lab"}, reopen: false}),
    setFavorite,
    listAlbums: vi.fn().mockResolvedValue({albums: [album], next_offset: null}),
    createAlbum: vi.fn().mockResolvedValue(album),
    changeAlbumMembership,
  });
  await act(async () => root.render(<App />));
  await click("Selecionar visíveis");
  expect(host.querySelector(".batch-toolbar")?.textContent).toContain("2 itens marcados");
  expect(host.querySelector(".workspace-status")?.textContent).toContain("2 selecionados");

  await click("☆ Favoritar marcados");
  expect(setFavorite).toHaveBeenCalledWith("first", true);
  expect(setFavorite).toHaveBeenCalledWith("second", true);
  expect(host.querySelector(".action-toast")?.textContent).toContain("2 imagens adicionadas aos favoritos.");

  await click("Adicionar marcados a álbum…");
  await click("Lote");
  expect(changeAlbumMembership).toHaveBeenCalledWith("alb-batch", "first", "add");
  expect(changeAlbumMembership).toHaveBeenCalledWith("alb-batch", "second", "add");
  expect(host.querySelector(".album-panel .action-toast")?.textContent).toContain("2 itens adicionados a “Lote”.");

  await click("Limpar seleção");
  expect(host.querySelector(".batch-toolbar")).toBeNull();
});
