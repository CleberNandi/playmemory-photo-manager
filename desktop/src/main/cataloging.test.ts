import { describe, expect, it, vi } from "vitest";
import { CatalogingController } from "./cataloging.js";

const id = "00000000-0000-4000-8000-000000000001";
const grant = "00000000-0000-4000-8000-000000000002";
const windowId = "00000000-0000-4000-8000-000000000003";
const next = "00000000-0000-4000-8000-000000000004";
function setup(enabled = true, choose = vi.fn(async (): Promise<string | null> => "/synthetic/media")) {
  let active = id;
  const backend = {request: vi.fn(async () => ({root_grant_id: grant}))};
  const libraries = {current: () => ({state: "active" as const, session: {session_id: active, library_handle: id, generation: 1, display_name: "synthetic"}, reopen: false}), isBusy: false, invalidate: vi.fn()};
  return {backend, libraries, controller: new CatalogingController(backend, libraries, windowId, enabled, choose), switch: () => {active = next;}};
}
describe("cataloging privileged IPC composition", () => {
  it("does not send any command after native cancel", async () => {
    const {controller, backend} = setup(true, vi.fn(async () => null));
    await expect(controller.choose(id)).resolves.toEqual({cancelled: true});
    expect(backend.request).not.toHaveBeenCalled();
  });
  it("derives window and native path exclusively in main", async () => {
    const {controller, backend} = setup();
    await controller.choose(id);
    expect(backend.request).toHaveBeenCalledWith("ingestion.select_root", {session_id:id, window_id:windowId, path:"/synthetic/media", recursive:true, identity_reviewed:true});
  });
  it("fails closed outside the lab and on stale session", async () => {
    await expect(setup(false).controller.choose(id)).rejects.toThrow("unavailable");
    await expect(setup().controller.choose(next)).rejects.toThrow("stale_session");
  });
  it("does not grant a late native selection after a library switch", async () => {
    let finish: (path: string) => void = () => undefined;
    const pending = new Promise<string>((resolve) => {finish = resolve;});
    const value = setup(true, vi.fn(() => pending));
    const selected = value.controller.choose(id);
    value.switch(); finish("/synthetic/media");
    await expect(selected).rejects.toThrow("stale_session");
    expect(value.backend.request).not.toHaveBeenCalled();
  });
  it("keeps the idempotency ID for identical prepare requests, and resets on a new session", async () => {
    const value = setup();
    await value.controller.prepare(id, grant, true);
    await value.controller.prepare(id, grant, true);
    const first = value.backend.request.mock.calls[0];
    expect(value.backend.request.mock.calls[1]).toEqual(first);
    value.switch(); await value.controller.prepare(next, grant, true);
    expect(value.backend.request.mock.calls[2]).not.toEqual(first);
  });
  it("rejects malformed operation/cursor/recursion values before transport", async () => {
    const {controller, backend} = setup();
    await expect(controller.prepare(id, grant, false)).rejects.toThrow("invalid_request");
    await expect(controller.operation("ingestion.cancel", id, "bad")).rejects.toThrow("invalid_request");
    await expect(controller.page(id, grant, "forged", 50)).rejects.toThrow("invalid_request");
    await expect(controller.page(id, grant, null, 51)).rejects.toThrow("invalid_request");
    expect(backend.request).not.toHaveBeenCalled();
  });
  it("invalidates state on unknown transport outcome without retrying mutation", async () => {
    const {controller, backend, libraries} = setup();
    backend.request.mockRejectedValue(new Error("private untrusted error"));
    await expect(controller.prepare(id, grant, true)).rejects.toThrow("unavailable");
    expect(libraries.invalidate).toHaveBeenCalledOnce();
    expect(backend.request).toHaveBeenCalledOnce();
  });
});
