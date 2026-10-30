import { randomUUID } from "node:crypto";
import type { PythonBackend } from "./backend.js";
import { canonicalId, emptyPreference, type LibraryPreference, type LibraryPreferences, validPath } from "./library-preferences.js";

export interface LibraryDescriptor { session_id: string; library_handle: string; generation: number; display_name: string }
export interface LibraryState { state: "active" | "no_library" | "unavailable" | "demo"; session: LibraryDescriptor | null; reopen: boolean; error?: string; warning?: string }
const errors = new Set(["not_found", "permission_denied", "corrupt", "incompatible", "upgrade_required", "busy", "unsafe_location", "internal_error", "invalid_request", "stale_session"]);
const failure = (error: unknown): string => {
  const code = (error as {code?: string})?.code;
  return code && errors.has(code) ? code : "internal_error";
};
type Backend = Pick<PythonBackend, "request">;
export interface LibraryDialogs { choose(create: boolean): Promise<string | null> }

export class LibraryController {
  private preference: LibraryPreference = emptyPreference();
  private state: LibraryState = { state: "no_library", session: null, reopen: false };
  private busy = false;
  private epoch = 0;
  constructor(private readonly backend: Backend, private readonly preferences: Pick<LibraryPreferences, "read" | "write">, private readonly dialogs: LibraryDialogs) {}
  current(): LibraryState { return structuredClone(this.state); }
  get isBusy(): boolean { return this.busy; }
  invalidate(): void { this.epoch++; this.state = {state: "unavailable", session: null, reopen: this.preference.reopen, error: "internal_error"}; }
  private async exclusive(action: () => Promise<void>): Promise<LibraryState> {
    if (this.busy) return {...this.current(), error: "busy"};
    this.busy = true;
    try { await action(); return this.current(); }
    catch (error) { return {...this.current(), error: failure(error)}; }
    finally { this.busy = false; }
  }
  private accept(raw: unknown): void {
    const p = raw as {state?: string; session?: LibraryDescriptor};
    if (!p || Object.keys(p).sort().join() !== "session,state" || (p.state !== "active" && p.state !== "no_library") || (p.state === "no_library" && p.session !== null)) throw new Error("invalid library state");
    if (p.state === "active" && (!p.session || Object.keys(p.session).sort().join() !== "display_name,generation,library_handle,session_id" || !canonicalId(p.session.session_id) || !canonicalId(p.session.library_handle) || !Number.isSafeInteger(p.session.generation) || p.session.generation < 0 || typeof p.session.display_name !== "string" || p.session.display_name.includes("/") || p.session.display_name.length > 4096)) throw new Error("invalid library descriptor");
    this.epoch++;
    this.state = {state: p.state, session: p.state === "active" ? p.session! : null, reopen: this.preference.reopen};
  }
  private async save(): Promise<void> {
    try { await this.preferences.write(this.preference); delete this.state.warning; }
    catch { this.state.warning = "preference_write_failed"; }
  }
  async initialize(): Promise<LibraryState> {
    return this.exclusive(async () => {
      this.accept(await this.backend.request("library.state"));
      try { this.preference = await this.preferences.read(); }
      catch { this.preference = emptyPreference(); this.state.warning = "preference_invalid"; }
      this.state.reopen = this.preference.reopen;
      if (this.preference.reopen && this.preference.last) {
        try { await this.activate(false, this.preference.last.path, this.preference.last.handle); }
        catch (error) { this.state = {state: "unavailable", session: null, reopen: true, error: failure(error)}; }
      }
    });
  }
  private async activate(create: boolean, path: string, handle: string): Promise<void> {
    if (!validPath(path)) throw Object.assign(new Error(), {code: "invalid_request"});
    try {
      const raw = await this.backend.request(create ? "library.create" : "library.open", {path, library_handle: handle});
      this.accept(raw);
    } catch (error) {
      if (!errors.has((error as {code?: string})?.code ?? "")) this.invalidate();
      throw error;
    }
    this.preference.last = {path, handle};
  }
  async choose(create: boolean): Promise<LibraryState> {
    return this.exclusive(async () => {
      const epoch = this.epoch;
      const path = await this.dialogs.choose(create);
      if (epoch !== this.epoch) throw Object.assign(new Error(), {code: "stale_session"});
      if (path === null) return;
      await this.activate(create, path, this.preference.last?.path === path ? this.preference.last.handle : randomUUID());
      await this.save();
    });
  }
  async close(sessionId: unknown): Promise<LibraryState> {
    return this.exclusive(async () => {
      this.requireSession(sessionId);
      try { this.accept(await this.backend.request("library.close", {session_id: sessionId})); }
      catch (error) { if (!errors.has((error as {code?: string})?.code ?? "")) this.invalidate(); throw error; }
    });
  }
  async setReopen(value: unknown): Promise<LibraryState> {
    return this.exclusive(async () => {
      if (typeof value !== "boolean") throw Object.assign(new Error(), {code: "invalid_request"});
      this.preference.reopen = value; this.state.reopen = value; await this.save();
    });
  }
  async forget(): Promise<LibraryState> {
    return this.exclusive(async () => {
      this.preference = emptyPreference(); this.state.reopen = false; await this.save();
    });
  }
  private requireSession(id: unknown): void {
    if (!canonicalId(id) || this.state.state !== "active" || id !== this.state.session?.session_id) throw Object.assign(new Error(), {code: "stale_session"});
  }
  async query(method: "gallery.list" | "asset.details" | "thumbnail.get" | "duplicates.list" | "duplicates.group", sessionId: unknown, params: Record<string, unknown>): Promise<unknown> {
    if (this.busy) throw Object.assign(new Error(), {code: "busy"});
    this.requireSession(sessionId);
    const epoch = this.epoch;
    const result = await this.backend.request(method, {...params, session_id: sessionId});
    if (epoch !== this.epoch) throw Object.assign(new Error(), {code: "stale_session"});
    return result;
  }
}
