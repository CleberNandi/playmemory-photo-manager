// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { requestThumbnail, thumbnailUrl } from "./thumbnails";
import { MediaCard } from "./MediaCard";
import type { GalleryItem } from "./types";
const png = {media_type: "image/png", width: 256, height: 160, base64: "iVBORw0KGgo="};
const flush = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };
it("limits concurrency, cancels queued work and ignores late results, surviving failure", async () => {
  const finish: ((value: unknown) => void)[] = [];
  const get = vi.fn(() => new Promise((resolve) => finish.push(resolve)));
  window.photoManager = {getThumbnail: get, listGallery: vi.fn(), retryGallery: vi.fn()};
  const receive = vi.fn();
  const cancel = Array.from({length: 8}, (_, i) => requestThumbnail(String(i), receive));
  await flush(); expect(get).toHaveBeenCalledTimes(4);
  cancel[0](); cancel[7](); finish.splice(0).forEach((resolve) => resolve(png));
  await flush(); expect(get).toHaveBeenCalledTimes(7); expect(receive).toHaveBeenCalledTimes(3);
  finish.splice(0).forEach((resolve) => resolve(null)); await flush();
  window.photoManager.getThumbnail = () => {throw new Error("private path");};
  requestThumbnail("failure", receive); await flush(); expect(receive).toHaveBeenLastCalledWith(null);
  delete window.photoManager;
});
it("rejects malformed format, dimensions and excessive payload", () => {
  for (const value of [{...png, media_type: "image/svg+xml"}, {...png, width: 999}, {...png, base64: "A".repeat(16388)}, {...png, base64: "file:///private"}]) expect(() => thumbnailUrl(value)).toThrow();
  expect(thumbnailUrl(null)).toBeNull(); expect(thumbnailUrl(png)).toMatch(/^data:image\/png;base64,/);
});
it("keeps fallback on load failure and prevents a previous asset updating a reused card", async () => {
  Object.assign(globalThis, {IS_REACT_ACT_ENVIRONMENT: true});
  const host = document.createElement("div"); const root = createRoot(host);
  let finish!: (value: unknown) => void;
  const get = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; })).mockResolvedValue(png);
  window.photoManager = {getThumbnail: get, listGallery: vi.fn(), retryGallery: vi.fn()};
  const item = (id: string): GalleryItem => ({asset_id: id, kind: "photo", media_type: null, created_at: "", availability: "no_location", representative_location: null, annotation: {title: id, favorite: false, rating: null}});
  await act(async () => {root.render(<MediaCard item={item("old")} />);});
  expect(host.querySelector("img")).toBeNull();
  await act(async () => {root.render(<MediaCard item={item("new")} />);});
  expect(host.querySelector("img")).not.toBeNull();
  await act(async () => {host.querySelector("img")!.dispatchEvent(new Event("error"));});
  expect(host.querySelector("img")).toBeNull();
  await act(async () => {finish(png); await flush();});
  expect(host.querySelector("img")).toBeNull();
  await act(async () => root.unmount()); delete window.photoManager;
});
