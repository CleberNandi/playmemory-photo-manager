// @vitest-environment jsdom
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, it, expect, vi } from "vitest";
import { App } from "./App";
import { useLibrarySession } from "./LibrarySession";
import { LibraryWorkspace } from "./LibraryWorkspace";
import type { LibraryState } from "./types";

function CatalogContent() { return <>{useLibrarySession()?.fileMenu}<div>Catalog content</div></>; }

let root: Root;
let host: HTMLDivElement;
beforeEach(() => {
  Object.assign(globalThis, {IS_REACT_ACT_ENVIRONMENT: true});
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
});
afterEach(async () => { await act(async () => root.unmount()); host.remove(); delete window.photoManager; });
const first: LibraryState = {state: "active", reopen: false, session: {session_id: "session-A", library_handle: "handle-A", generation: 1, display_name: "A.sqlite3"}};
async function click(label: string) { await act(async () => { [...host.querySelectorAll("button")].find((b) => b.textContent === label)!.click(); }); }

it("starts without a library and never renders catalog children until a selection is active", async () => {
  const listGallery = vi.fn();
  window.photoManager = {listGallery, retryGallery: vi.fn(), getLibraryState: vi.fn().mockResolvedValue({state: "no_library", session: null, reopen: false}), chooseCreateLibrary: vi.fn().mockResolvedValue(first)};
  await act(async () => root.render(<LibraryWorkspace><CatalogContent /></LibraryWorkspace>));
  expect(host.textContent).toContain("Escolha uma biblioteca"); expect(host.textContent).not.toContain("Catalog content");
  expect(listGallery).not.toHaveBeenCalled();
  await click("Criar biblioteca"); expect(host.textContent).toContain("Catalog content"); expect(host.textContent).toContain("A.sqlite3");
});

it("preserves children on cancellation and remounts them for a new session even with the same library name", async () => {
  const mounts = vi.fn(); const unmounts = vi.fn();
  function Child() { useEffect(() => {mounts(); return () => {unmounts();};}, []); return <CatalogContent />; }
  const open = vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce({...first, session: {...first.session!, session_id: "session-B"}});
  window.photoManager = {listGallery: vi.fn(), retryGallery: vi.fn(), getLibraryState: vi.fn().mockResolvedValue(first), chooseOpenLibrary: open};
  await act(async () => root.render(<LibraryWorkspace><Child /></LibraryWorkspace>));
  await click("Abrir biblioteca"); expect(mounts).toHaveBeenCalledTimes(1); expect(unmounts).not.toHaveBeenCalled();
  await click("Abrir biblioteca"); expect(mounts).toHaveBeenCalledTimes(2); expect(unmounts).toHaveBeenCalledOnce();
});

it("reports preference failure while keeping the active catalog and clears it on close", async () => {
  window.photoManager = {listGallery: vi.fn(), retryGallery: vi.fn(), getLibraryState: vi.fn().mockResolvedValue(first), setReopenLibrary: vi.fn().mockResolvedValue({...first, warning: "preference_write_failed"}), closeLibrary: vi.fn().mockResolvedValue({state: "no_library", session: null, reopen: false})};
  await act(async () => root.render(<LibraryWorkspace><CatalogContent /></LibraryWorkspace>));
  await act(async () => host.querySelector<HTMLInputElement>("input")!.click());
  expect(host.textContent).toContain("preferência não foi salva"); expect(host.textContent).toContain("Catalog content");
  await click("Fechar biblioteca"); expect(host.textContent).not.toContain("Catalog content");
});

it("shows preparation on demand and removes it on session close", async () => {
  window.photoManager = {listGallery: vi.fn().mockResolvedValue({items: [], next_cursor: null, has_more: false}), retryGallery: vi.fn(), getLibraryState: vi.fn().mockResolvedValue({...first, cataloging_enabled: true}), closeLibrary: vi.fn().mockResolvedValue({state: "no_library", session: null, reopen: false})};
  await act(async () => root.render(<App />));
  expect(host.querySelector<HTMLElement>(".preparation-workflow")!.hidden).toBe(true);
  await click("+ Adicionar pastas");
  expect(host.querySelector<HTMLElement>(".preparation-workflow")!.hidden).toBe(false);
  expect(host.querySelector('[aria-label="Preparar catalogação"]')).not.toBeNull();
  await click("Fechar biblioteca"); expect(host.querySelector('[aria-label="Preparar catalogação"]')).toBeNull();
});

it("confirms the named album before deleting it and returns to the album list", async () => {
  const album = {id: "album-a", name: "Viagem"};
  const listGallery = vi.fn().mockResolvedValue({items: [], next_cursor: null, has_more: false});
  const deleteAlbum = vi.fn().mockResolvedValue({changed: true});
  window.photoManager = {
    listGallery, retryGallery: vi.fn(), getLibraryState: vi.fn().mockResolvedValue(first),
    listAlbums: vi.fn().mockResolvedValue({albums: [album], next_offset: null}),
    createAlbum: vi.fn(), changeAlbumMembership: vi.fn(), deleteAlbum,
  };
  await act(async () => root.render(<App />));
  await click("Álbuns");
  await click("Viagem");
  expect(host.querySelector("h1")?.textContent).toBe("Viagem");
  await click("Excluir álbum");
  expect(host.querySelector("legend")?.textContent).toBe("Excluir o álbum “Viagem”?");
  await click("Cancelar");
  expect(deleteAlbum).not.toHaveBeenCalled();
  await click("Excluir álbum");
  await click("Confirmar exclusão");
  expect(deleteAlbum).toHaveBeenCalledExactlyOnceWith(album.id);
  expect(host.querySelector("h1")?.textContent).toBe("Álbuns");
  expect(listGallery).toHaveBeenLastCalledWith({pageSize: 24});
});

it("refreshes connected media on demand in the active library", async () => {
  const listMediaDevices = vi.fn().mockResolvedValueOnce({status: "ready", devices: [
    {id: "imaging:1-2", name: "Synthetic Camera", kind: "imaging"},
    {id: "storage:sdb", name: "Synthetic Card", kind: "storage"},
  ], total_count: 2}).mockResolvedValueOnce({status: "ready", devices: [], total_count: 0});
  window.photoManager = {
    getLibraryState: vi.fn().mockResolvedValue(first),
    listGallery: vi.fn().mockResolvedValue({items: [], next_cursor: null, has_more: false}),
    retryGallery: vi.fn(), listMediaDevices,
  };
  await act(async () => root.render(<App />));
  expect(listMediaDevices).not.toHaveBeenCalled();
  await act(async () => [...host.querySelectorAll("summary")].find(item=>item.textContent==="Câmeras e mídias")!.click());
  await click("Detectar dispositivos");
  expect(host.querySelector(".media-devices")?.textContent).toContain("Synthetic Camera");
  expect(host.querySelector(".media-devices")?.textContent).toContain("Synthetic Card");
  await click("Atualizar dispositivos");
  expect(host.querySelector(".media-devices")).toBeNull();
  expect(host.textContent).toContain("Nenhum dispositivo compatível detectado");
});
