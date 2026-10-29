// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { DetailsContent } from "./AssetDetailsPanel";
import type { AssetDetails, DetailsResult, GalleryItem } from "./types";
let host: HTMLDivElement; let root: Root;
const item = (id: string): GalleryItem => ({asset_id: id, kind: "photo", media_type: null, created_at: "synthetic", availability: "no_location", annotation: {title: id, favorite: false, rating: null}, representative_location: null});
const details = (id: string): AssetDetails => ({asset: {id, kind: "photo", sha256: null, hash_state: "absent", byte_size: null, media_type: null, status: "active", created_at: "synthetic"}, capture: null, annotation: null, tags: [], metadata: [], metadata_state: "not_extracted", locations: [], locations_truncated: false, availability: "no_location"});
beforeEach(() => { Object.assign(globalThis, {IS_REACT_ACT_ENVIRONMENT: true}); host = document.createElement("div"); document.body.append(host); root = createRoot(host); });
afterEach(async () => { await act(async () => root.unmount()); host.remove(); delete window.photoManager; });
const mount = async (getAssetDetails: (id: string) => Promise<DetailsResult>) => {
  window.photoManager = {listGallery: vi.fn().mockResolvedValue({items: [item("first"), item("second")], next_cursor: "preserved", has_more: true}), retryGallery: vi.fn().mockResolvedValue({items: [], has_more: false, next_cursor: null}), getAssetDetails};
  await act(async () => root.render(<App />));
};
const select = async (index = 0) => { await act(async () => host.querySelectorAll<HTMLButtonElement>(".card-select")[index].click()); };
it("opens read-only details with visible selection, focuses close, and Escape restores origin", async () => {
  await mount(async (id) => ({status: "ready", details: details(id)}));
  await select();
  expect(host.querySelector('[aria-pressed="true"]')).not.toBeNull();
  const close = host.querySelector<HTMLButtonElement>(".asset-details button")!;
  expect(document.activeElement).toBe(close);
  expect(host.textContent).toContain("Metadata não extraída");
  expect(host.querySelectorAll(".media-card")).toHaveLength(2);
  expect(host.querySelector(".pagination button")?.textContent).toBe("Carregar mais");
  await act(async () => close.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true})));
  expect(host.querySelector(".asset-details")).toBeNull();
  expect(document.activeElement).toBe(host.querySelector(".card-select"));
});
it("ignores a previous delayed response and a response after close", async () => {
  const pending: Record<string, (result: DetailsResult) => void> = {};
  await mount((id) => new Promise((resolve) => {pending[id] = resolve;}));
  await select(); expect(host.textContent).toContain("Carregando detalhes");
  await select(1);
  await act(async () => pending.second({status: "ready", details: details("second")}));
  await act(async () => pending.first({status: "ready", details: details("first")}));
  expect(host.querySelector(".asset-details dl")?.textContent).toContain("second");
  expect(host.querySelector(".asset-details dl")?.textContent).not.toContain("first");
  await act(async () => host.querySelector<HTMLButtonElement>(".asset-details button")!.click());
  expect(host.querySelector(".asset-details")).toBeNull();
});
it("sanitizes rejection and reconnects the backend on retry", async () => {
  const get = vi.fn().mockRejectedValueOnce(new Error("/private/secret")).mockResolvedValueOnce({status: "ready", details: details("first")});
  await mount(get); await select();
  expect(host.querySelector(".asset-details [role=alert]")).not.toBeNull();
  expect(host.textContent).not.toContain("private");
  await act(async () => host.querySelector<HTMLButtonElement>(".asset-details [role=alert] button")!.click());
  expect(window.photoManager?.retryGallery).toHaveBeenCalledOnce();
  expect(host.textContent).toContain("Metadata não extraída");
});
it("shows not-found without treating it as empty metadata", async () => {
  await mount(async () => ({status: "not_found"})); await select();
  expect(host.textContent).toContain("Asset não encontrado");
  expect(host.textContent).not.toContain("Metadata não extraída");
});
it("renders truncation, temporal provenance, literal long text, and preserved conflicts", async () => {
  const d = details("synthetic"); d.locations_truncated = true;
  d.capture = {local_value: "2026-01", precision: "month", timezone_state: "unknown", offset_minutes: null, timezone_name: null, source_kind: "synthetic-lab", metadata_id: "lab", selection_reason: "fixture only"};
  d.metadata_state = "extracted";
  d.metadata = [{id: "lab", namespace: "synthetic", key: "example", source: "synthetic-lab", source_key: "fixture", raw_value: "<script>" + "x".repeat(1000), interpreted_value: null, value_type: "text", temporal_local_value: null, temporal_precision: null, timezone_state: null, utc_offset_minutes: null, timezone_name: null, extractor_version: "lab-v1", extracted_at: "2026-01", parse_error: null, conflict_group: "lab-conflict", is_conflicting: true}];
  await act(async () => root.render(<DetailsContent details={d} />));
  expect(host.textContent).toContain("primeiras 100"); expect(host.textContent).toContain("synthetic-lab"); expect(host.textContent).toContain("Conflito preservado"); expect(host.querySelector("script")).toBeNull(); expect(host.textContent).toContain("month");
});
it("discards pending details after closing and reopening a different asset", async () => {
  let finish!: (result: DetailsResult) => void;
  await mount((id) => id === "first" ? new Promise((resolve) => {finish = resolve;}) : Promise.resolve({status: "ready", details: details(id)}));
  await select();
  await act(async () => host.querySelector<HTMLButtonElement>(".asset-details button")!.click());
  await select(1);
  await act(async () => finish({status: "ready", details: details("first")}));
  expect(host.querySelector(".asset-details dl")?.textContent).toContain("second");
  expect(host.querySelector(".asset-details dl")?.textContent).not.toContain("first");
});
