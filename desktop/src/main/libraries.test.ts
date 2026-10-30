import { describe, it, expect, vi } from "vitest";
import { randomUUID } from "node:crypto";
import { LibraryController } from "./libraries.js";
import { emptyPreference } from "./library-preferences.js";
import { trustedSender } from "./trusted-ipc.js";

function fixture() {
  const preferences = {read: vi.fn().mockResolvedValue(emptyPreference()), write: vi.fn().mockResolvedValue(undefined)};
  const dialogs = {choose: vi.fn().mockResolvedValue("/synthetic/catalog")};
  const request = vi.fn(async (method: string, p: Record<string, unknown> = {}) => {
    if (method === "library.state" || method === "library.close") return {state: "no_library", session: null};
    if (method === "library.open" || method === "library.create") return {state: "active", session: {session_id: randomUUID(), library_handle: p.library_handle, generation: 1, display_name: "catalog"}};
    return {items: []};
  });
  return {preferences, dialogs, request, controller: new LibraryController({request}, preferences, dialogs)};
}

describe("library controller", () => {
  it("does not create or open before a native selection; cancel preserves session and preferences", async () => {
    const f = fixture();
    await f.controller.initialize();
    expect(f.request).toHaveBeenCalledTimes(1);
    const first = await f.controller.choose(true);
    expect(JSON.stringify(first)).not.toContain("/synthetic");
    f.preferences.write.mockClear(); f.dialogs.choose.mockResolvedValueOnce(null);
    expect(await f.controller.choose(false)).toEqual(first);
    expect(f.preferences.write).not.toHaveBeenCalled();
    expect(f.request).toHaveBeenCalledTimes(2);
  });
  it("preserves session on semantic failure, but invalidates on unknown command outcome", async () => {
    const f = fixture(); await f.controller.initialize();
    const first = await f.controller.choose(true);
    f.request.mockRejectedValueOnce(Object.assign(new Error("private path"), {code: "corrupt"}));
    expect((await f.controller.choose(false)).session).toEqual(first.session);
    f.request.mockRejectedValueOnce(new Error("private timeout"));
    const failed = await f.controller.choose(false);
    expect(failed.state).toBe("unavailable"); expect(failed.session).toBeNull();
    expect(JSON.stringify(failed)).not.toContain("private");
  });
  it("keeps the active catalog when saving preference fails; close preserves last; forget is separate", async () => {
    const f = fixture(); await f.controller.initialize();
    f.preferences.write.mockRejectedValueOnce(new Error());
    const state = await f.controller.choose(true);
    expect(state.state).toBe("active"); expect(state.warning).toBe("preference_write_failed");
    await f.controller.close(state.session!.session_id);
    const calls = f.preferences.write.mock.calls.length;
    await f.controller.forget();
    expect(f.preferences.write.mock.calls.length).toBe(calls + 1);
    expect(f.preferences.write).toHaveBeenLastCalledWith(emptyPreference());
  });
  it("reopens only when opted in, using open and a fresh session", async () => {
    const f = fixture(); const handle = randomUUID();
    f.preferences.read.mockResolvedValue({version: 1, reopen: true, last: {path: "/synthetic/catalog", handle}});
    const state = await f.controller.initialize();
    expect(state.state).toBe("active");
    expect(f.request).toHaveBeenLastCalledWith("library.open", {path: "/synthetic/catalog", library_handle: handle});
    expect(f.preferences.write).not.toHaveBeenCalled();
  });
  it("rejects stale sessions and late queries across a library switch", async () => {
    const f = fixture(); await f.controller.initialize();
    const first = await f.controller.choose(true);
    let finish!: (value: {items: never[]}) => void;
    f.request.mockImplementationOnce(() => new Promise((resolve) => {finish = resolve;}));
    const query = f.controller.query("gallery.list", first.session!.session_id, {});
    const rejected = expect(query).rejects.toMatchObject({code: "stale_session"});
    await f.controller.choose(false);
    finish({items: []}); await rejected;
    await expect(f.controller.query("gallery.list", first.session!.session_id, {})).rejects.toMatchObject({code: "stale_session"});
  });
  it("blocks concurrent lifecycle actions while a dialog is pending", async () => {
    const f = fixture(); await f.controller.initialize();
    let cancel!: (value: null) => void;
    f.dialogs.choose.mockImplementationOnce(() => new Promise((resolve) => {cancel = resolve;}));
    const choosing = f.controller.choose(true);
    expect((await f.controller.choose(false)).error).toBe("busy");
    expect((await f.controller.forget()).error).toBe("busy");
    cancel(null); await choosing;
  });
  it("keeps a previously admitted query valid while a selection is only pending and then cancelled", async () => {
    const f = fixture(); await f.controller.initialize();
    const first = await f.controller.choose(true);
    let finish!: (value: {items: never[]}) => void;
    f.request.mockImplementationOnce(() => new Promise((resolve) => {finish = resolve;}));
    const query = f.controller.query("gallery.list", first.session!.session_id, {});
    let cancel!: (value: null) => void;
    f.dialogs.choose.mockImplementationOnce(() => new Promise((resolve) => {cancel = resolve;}));
    const choosing = f.controller.choose(false);
    finish({items: []}); expect(await query).toEqual({items: []});
    cancel(null); expect(await choosing).toEqual(first);
  });
});

it("rejects foreign windows, subframes, unexpected origins and destroyed senders", () => {
  const frame = {url: "file:///synthetic/index.html"};
  const owner = {webContents: {mainFrame: frame}, isDestroyed: () => false};
  const event = {sender: owner.webContents, senderFrame: frame};
  expect(trustedSender(event, owner, frame.url)).toBe(true);
  expect(trustedSender({...event, sender: {}}, owner, frame.url)).toBe(false);
  expect(trustedSender({...event, senderFrame: {url: frame.url}}, owner, frame.url)).toBe(false);
  expect(trustedSender(event, owner, "https://other.invalid")).toBe(false);
  expect(trustedSender(event, {...owner, isDestroyed: () => true}, frame.url)).toBe(false);
});
