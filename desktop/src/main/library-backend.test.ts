import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { expect, it } from "vitest";
import { PythonBackend } from "./backend.js";
import type { LibraryState } from "./libraries.js";

it("runs the real supervised Python lifecycle offline and rejects stale sessions after close", async () => {
  const folder = await mkdtemp(join(tmpdir(), "pm-backend-"));
  const backend = new PythonBackend();
  try {
    await backend.start();
    expect(await backend.request("library.state")).toEqual({state: "no_library", session: null});
    const state = await backend.request("library.create", {path: join(folder, "catalog.sqlite3"), library_handle: randomUUID()}) as LibraryState;
    expect(state.state).toBe("active");
    const session_id = state.session!.session_id;
    expect(await backend.request("gallery.list", {session_id})).toEqual({items: [], next_cursor: null, has_more: false});
    await expect(backend.request("gallery.list", {session_id, page_size: true})).rejects.toMatchObject({code: "invalid_request"});
    await backend.request("library.close", {session_id});
    await expect(backend.request("gallery.list", {session_id})).rejects.toMatchObject({code: "stale_session"});
    await backend.restart();
    expect(await backend.request("library.state")).toEqual({state: "no_library", session: null});
    const reopened = await backend.request("library.open", {path: join(folder, "catalog.sqlite3"), library_handle: randomUUID()}) as LibraryState;
    expect(reopened.session!.session_id).not.toBe(session_id);
  } finally { await backend.stop(); await rm(folder, {recursive: true, force: true}); }
}, 20000);
