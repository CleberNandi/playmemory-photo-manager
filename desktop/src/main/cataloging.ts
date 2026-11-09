import { randomUUID } from "node:crypto";
import type { PythonBackend } from "./backend.js";
import type { LibraryController } from "./libraries.js";
import { canonicalId, validPath } from "./library-preferences.js";

const known = new Set(["invalid_request", "stale_session", "stale_grant", "unsafe_location", "root_changed", "permission_denied", "resource_limit", "busy", "unavailable", "not_found", "outcome_unknown"]);
const reject = (code: string): never => { throw Object.assign(new Error(code), {code}); };

export class CatalogingController {
  private choosing = false;
  private session: string | null = null;
  private readonly pending = new Map<string, Promise<unknown>>();
  private readonly requests = new Map<string, string>();
  private readonly applicationRequests = new Map<string, string>();
  private readonly applicationPending = new Map<string, Promise<unknown>>();
  constructor(
    private readonly backend: Pick<PythonBackend, "request">,
    private readonly libraries: Pick<LibraryController, "current" | "isBusy" | "invalidate">,
    private readonly windowId: string,
    private readonly enabled: boolean,
    private readonly choosePath: () => Promise<string | null>,
    private readonly confirmApplication: (count: number) => Promise<boolean> = async () => false,
  ) {}
  private require(id: unknown, allowBusy = false): string {
    if (!this.enabled) return reject("unavailable");
    if (this.libraries.isBusy && !allowBusy) return reject("busy");
    const state = this.libraries.current();
    if (!canonicalId(id) || state.state !== "active" || state.session?.session_id !== id) return reject("stale_session");
    if (this.session !== id) { this.requests.clear(); this.pending.clear(); this.applicationRequests.clear(); this.applicationPending.clear(); this.session = id as string; }
    return id as string;
  }
  private async send(method: Parameters<PythonBackend["request"]>[0], id: unknown, params: Record<string, unknown>, allowBusy = false): Promise<unknown> {
    const session = this.require(id, allowBusy);
    try {
      const result = await this.backend.request(method, {...params, session_id: session, window_id: this.windowId});
      this.require(session, true); // Discard a late response after a switch or backend failure.
      return result;
    } catch (error) {
      const code = (error as {code?: string})?.code;
      if (code && known.has(code)) return reject(code);
      this.libraries.invalidate();
      return reject("unavailable");
    }
  }
  async choose(id: unknown): Promise<unknown> {
    const session = this.require(id);
    if (this.choosing) return reject("busy");
    this.choosing = true;
    try {
      const path = await this.choosePath();
      this.require(session);
      if (path === null) return {cancelled: true};
      if (!validPath(path)) return reject("invalid_request");
      return await this.send("ingestion.select_root", session, {path, recursive: true, identity_reviewed: true});
    } catch (error) {
      const code = (error as {code?: string})?.code;
      return reject(code && known.has(code) ? code : "unavailable");
    } finally { this.choosing = false; }
  }
  prepare(id: unknown, grant: unknown, recursive: unknown): Promise<unknown> {
    this.require(id);
    if (!canonicalId(grant) || recursive !== true) return Promise.reject(new Error("invalid_request"));
    const key = `${id}:${grant}`;
    const pending = this.pending.get(key);
    if (pending) return pending;
    if (!this.requests.has(key)) {
      if (this.requests.size === 32) return Promise.reject(new Error("resource_limit"));
      this.requests.set(key, randomUUID());
    }
    const admission = this.send("ingestion.prepare", id, {root_grant_id: grant, recursive: true, client_request_id: this.requests.get(key)})
      .catch((error: unknown) => { this.requests.delete(key); throw error; })
      .finally(() => { this.pending.delete(key); });
    this.pending.set(key, admission);
    return admission;
  }
  apply(id: unknown, proposal: unknown, selection: unknown): Promise<unknown> {
    this.require(id);
    if (!canonicalId(proposal) || !Array.isArray(selection) || selection.length < 1 || selection.length > 100 || selection.some((value) => !canonicalId(value)) || new Set(selection).size !== selection.length) return Promise.reject(new Error("invalid_request"));
    const ids = [...selection].sort() as string[];
    const key = `${id}:${proposal}:${ids.join(",")}`;
    const previous = this.applicationPending.get(key);
    if (previous) return previous;
    const execute = async () => {
      if (this.choosing) return reject("busy");
      if (!this.applicationRequests.has(key) && this.applicationRequests.size === 32) return reject("resource_limit");
      this.choosing = true;
      let confirmed: boolean;
      try { confirmed = await this.confirmApplication(ids.length); this.require(id); }
      finally { this.choosing = false; }
      if (!confirmed) return {cancelled: true};
      if (!this.applicationRequests.has(key)) this.applicationRequests.set(key, randomUUID());
      try { return await this.send("ingestion.apply", id, {proposal_id: proposal, candidate_ids: ids, client_request_id: this.applicationRequests.get(key)}); }
      catch (error) { if ((error as {code?: string}).code === "unavailable") return reject("outcome_unknown"); throw error; }
    };
    const pending = execute().finally(() => { this.applicationPending.delete(key); });
    this.applicationPending.set(key, pending);
    return pending;
  }
  applicationStatus(id: unknown, command: unknown): Promise<unknown> {
    this.require(id, true);
    if (!canonicalId(command)) return Promise.reject(new Error("invalid_request"));
    return this.send("ingestion.application_status", id, {command_id: command}, true);
  }
  operation(method: "ingestion.status" | "ingestion.cancel", id: unknown, operation: unknown): Promise<unknown> {
    this.require(id);
    if (!canonicalId(operation)) return Promise.reject(new Error("invalid_request"));
    return this.send(method, id, {operation_id: operation});
  }
  page(id: unknown, proposal: unknown, cursor: unknown, size: unknown): Promise<unknown> {
    this.require(id);
    if (!canonicalId(proposal) || (cursor !== null && (typeof cursor !== "string" || !/^[a-f0-9]{64}$/.test(cursor))) || !Number.isInteger(size) || Number(size) < 1 || Number(size) > 50) return Promise.reject(new Error("invalid_request"));
    return this.send("ingestion.page", id, {proposal_id: proposal, cursor, page_size: size});
  }
}
