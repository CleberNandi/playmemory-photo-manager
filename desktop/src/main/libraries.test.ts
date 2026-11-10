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

it("scopes favorite commands and rejects late responses after a library switch",async()=>{
 const f=fixture();await f.controller.initialize();const state=await f.controller.choose(true);const asset=randomUUID();
 await expect(f.controller.setFavorite(randomUUID(),asset,true)).rejects.toMatchObject({code:"stale_session"});
 let finish!:(value:{items:never[]})=>void;f.request.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 const save=f.controller.setFavorite(state.session!.session_id,asset,true);const rejected=expect(save).rejects.toMatchObject({code:"stale_session"});
 expect(f.request).toHaveBeenLastCalledWith("annotation.favorite",{session_id:state.session!.session_id,asset_id:asset,favorite:true});
 await f.controller.choose(true);finish({items:[]});await rejected;
});

it("creates the managed library only after a proven not_found and saves automatic reopen",async()=>{
 const f=fixture();const original=f.request.getMockImplementation()!;
 f.request.mockImplementation(async(method,p={})=>{if(method==="library.open")throw Object.assign(new Error(),{code:"not_found"});return original(method,p);});
 const controller=new LibraryController({request:f.request},f.preferences,f.dialogs,async()=>"/synthetic/profile/principal.sqlite3");
 const state=await controller.initialize();expect(state.state).toBe("active");expect(state.session!.display_name).toBe("Minha biblioteca");expect(state.reopen).toBe(true);expect(f.dialogs.choose).not.toHaveBeenCalled();expect(f.preferences.write).toHaveBeenCalledWith(expect.objectContaining({reopen:true,last:expect.objectContaining({path:"/synthetic/profile/principal.sqlite3"})}));
});
it("reopens an existing managed library and never recreates a corrupt one",async()=>{
 const f=fixture();const controller=new LibraryController({request:f.request},f.preferences,f.dialogs,async()=>"/synthetic/profile/principal.sqlite3");
 await controller.initialize();expect(f.request.mock.calls.some(([method])=>method==="library.create")).toBe(false);
 const failed=fixture();const original=failed.request.getMockImplementation()!;failed.request.mockImplementation(async(method,p={})=>{if(method==="library.open")throw Object.assign(new Error(),{code:"corrupt"});return original(method,p);});
 const second=new LibraryController({request:failed.request},failed.preferences,failed.dialogs,async()=>"/synthetic/profile/principal.sqlite3");const state=await second.initialize();expect(state.state).toBe("unavailable");expect(state.error).toBe("corrupt");expect(failed.request.mock.calls.some(([method])=>method==="library.create")).toBe(false);
});

it.each([false,true])("recovers a deleted preferred catalog using the managed library (existing=%s)",async(existing)=>{
 const f=fixture();const original=f.request.getMockImplementation()!;const managed="/synthetic/profile/principal.sqlite3";
 f.preferences.read.mockResolvedValue({version:1,reopen:false,last:{path:"/synthetic/deleted.sqlite3",handle:randomUUID()}});
 f.request.mockImplementation(async(method,p={})=>{if(method==="library.open"&&(p.path!==managed||!existing))throw Object.assign(new Error(),{code:"not_found"});return original(method,p);});
 const controller=new LibraryController({request:f.request},f.preferences,f.dialogs,async()=>managed);
 const state=await controller.initialize();expect(state.state).toBe("active");expect(state.session!.display_name).toBe("Minha biblioteca");expect(f.dialogs.choose).not.toHaveBeenCalled();
 const creates=f.request.mock.calls.filter(([method])=>method==="library.create");expect(creates).toHaveLength(existing?0:1);if(!existing)expect(creates[0][1]?.path).toBe(managed);
 expect(f.preferences.write).toHaveBeenCalledWith(expect.objectContaining({last:expect.objectContaining({path:managed})}));
});
it.each(["corrupt","permission_denied","incompatible"])("does not silently replace a preferred catalog on %s",async(code)=>{
 const f=fixture();const original=f.request.getMockImplementation()!;
 f.preferences.read.mockResolvedValue({version:1,reopen:true,last:{path:"/synthetic/previous.sqlite3",handle:randomUUID()}});
 f.request.mockImplementation(async(method,p={})=>{if(method==="library.open")throw Object.assign(new Error(),{code});return original(method,p);});
 const controller=new LibraryController({request:f.request},f.preferences,f.dialogs,async()=>"/synthetic/profile/principal.sqlite3");
 expect(await controller.initialize()).toMatchObject({state:"unavailable",error:code});expect(f.request.mock.calls.filter(([method])=>method==="library.open")).toHaveLength(1);expect(f.request.mock.calls.some(([method])=>method==="library.create")).toBe(false);
});
