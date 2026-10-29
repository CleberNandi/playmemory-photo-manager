// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { GalleryPage } from "./types";

const empty: GalleryPage = {items: [], next_cursor: null, has_more: false};
let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  Object.assign(globalThis, {IS_REACT_ACT_ENVIRONMENT: true});
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
});
afterEach(async () => { await act(async () => root.unmount()); host.remove(); delete window.photoManager; });
const mount = async () => { await act(async () => root.render(<App />)); };
const retry = async () => { await act(async () => host.querySelector<HTMLButtonElement>(".primary-button")!.click()); };
describe("gallery lifecycle", () => {
  it("shows loading while the bridge is pending", async () => {
    window.photoManager = {listGallery: () => new Promise(() => {}), retryGallery: vi.fn()};
    await mount(); expect(host.textContent).toContain("Abrindo o catálogo"); expect(host.querySelector('[aria-busy="true"]')).not.toBeNull();
  });
  it("shows the empty library after a real response shape", async () => {
    window.photoManager = {listGallery: vi.fn().mockResolvedValue(empty), retryGallery: vi.fn()};
    await mount(); expect(host.textContent).toContain("Sua biblioteca está vazia");
  });
  it("renders populated data without adding card tab stops", async () => {
    window.photoManager = {listGallery: vi.fn().mockResolvedValue({...empty, items: [{asset_id: "synthetic", kind: "photo", availability: "offline", annotation: {title: "   "}, representative_location: {relative_path: " "}}]}), retryGallery: vi.fn()};
    await mount(); expect(host.querySelector(".media-card h3")?.textContent).toBe("Sem título"); expect(host.querySelector(".media-card")?.hasAttribute("tabindex")).toBe(false); expect(host.textContent).toContain("Raiz offline");
  });
  it.each(["sync", "async", "missing"])("recovers from %s bridge failure with retry", async (failure) => {
    const success = vi.fn().mockResolvedValue(empty);
    if (failure !== "missing") window.photoManager = {listGallery: () => { if (failure === "sync") throw new Error("private details"); return Promise.reject(new Error("private details")); }, retryGallery: success};
    await mount(); expect(host.querySelector('[role="alert"]')).not.toBeNull(); expect(host.textContent).not.toContain("private details");
    if (failure === "missing") { await retry(); expect(host.querySelector('[role="alert"]')).not.toBeNull(); window.photoManager = {listGallery: success, retryGallery: success}; }
    await retry(); expect(success).toHaveBeenCalledOnce(); expect(host.textContent).toContain("Sua biblioteca está vazia");
  });
  it("handles a synchronous retry failure", async () => {
    window.photoManager = {listGallery: vi.fn().mockRejectedValue(new Error()), retryGallery: () => {throw new Error();}};
    await mount(); await retry(); expect(host.querySelector('[role="alert"]')).not.toBeNull();
  });
});
