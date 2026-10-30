// @vitest-environment jsdom
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, it, expect, vi } from "vitest";
import { LibraryWorkspace } from "./LibraryWorkspace";
import type { LibraryState } from "./types";

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
  await act(async () => root.render(<LibraryWorkspace><div>Catalog content</div></LibraryWorkspace>));
  expect(host.textContent).toContain("Escolha uma biblioteca"); expect(host.textContent).not.toContain("Catalog content");
  expect(listGallery).not.toHaveBeenCalled();
  await click("Criar biblioteca"); expect(host.textContent).toContain("Catalog content"); expect(host.textContent).toContain("A.sqlite3");
});

it("preserves children on cancellation and remounts them for a new session even with the same library name", async () => {
  const mounts = vi.fn(); const unmounts = vi.fn();
  function Child() { useEffect(() => {mounts(); return () => {unmounts();};}, []); return <div>Catalog content</div>; }
  const open = vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce({...first, session: {...first.session!, session_id: "session-B"}});
  window.photoManager = {listGallery: vi.fn(), retryGallery: vi.fn(), getLibraryState: vi.fn().mockResolvedValue(first), chooseOpenLibrary: open};
  await act(async () => root.render(<LibraryWorkspace><Child /></LibraryWorkspace>));
  await click("Abrir biblioteca"); expect(mounts).toHaveBeenCalledTimes(1); expect(unmounts).not.toHaveBeenCalled();
  await click("Abrir biblioteca"); expect(mounts).toHaveBeenCalledTimes(2); expect(unmounts).toHaveBeenCalledOnce();
});

it("reports preference failure while keeping the active catalog and clears it on close", async () => {
  window.photoManager = {listGallery: vi.fn(), retryGallery: vi.fn(), getLibraryState: vi.fn().mockResolvedValue(first), setReopenLibrary: vi.fn().mockResolvedValue({...first, warning: "preference_write_failed"}), closeLibrary: vi.fn().mockResolvedValue({state: "no_library", session: null, reopen: false})};
  await act(async () => root.render(<LibraryWorkspace><div>Catalog content</div></LibraryWorkspace>));
  await act(async () => host.querySelector<HTMLInputElement>("input")!.click());
  expect(host.textContent).toContain("preferência não foi salva"); expect(host.textContent).toContain("Catalog content");
  await click("Fechar biblioteca"); expect(host.textContent).not.toContain("Catalog content");
});
