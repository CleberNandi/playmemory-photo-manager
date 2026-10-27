import { randomBytes, randomUUID } from "node:crypto";
import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { resolve } from "node:path";

type Pending = { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: NodeJS.Timeout };
type ResponseMessage = { id?: string; ok?: boolean; result?: unknown; error?: { code?: string; message?: string }; event?: string };

export class PythonBackend extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null;
  private readonly pending = new Map<string, Pending>();
  private token = "";
  private buffer = "";
  private readyPromise: Promise<void> | null = null;
  private markReady: (() => void) | null = null;
  private failReady: ((error: Error) => void) | null = null;
  private stopping = false;

  start(repositoryRoot = resolve(import.meta.dirname, "../../..")): Promise<void> {
    if (this.child) return Promise.reject(new Error("backend is already running"));
    this.token = randomBytes(32).toString("hex");
    this.readyPromise = new Promise((resolveReady, rejectReady) => {
      this.markReady = resolveReady;
      this.failReady = rejectReady;
    });
    this.child = spawn("uv", ["run", "python", "-m", "playmemories_photo_manager.desktop.bridge"], {
      cwd: repositoryRoot,
      env: { ...process.env, PLAYMEMORIES_BRIDGE_TOKEN: this.token },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.child.stdout.setEncoding("utf8");
    this.child.stdout.on("data", (chunk: string) => this.consume(chunk));
    this.child.stderr.on("data", () => this.emit("diagnostic", "backend reported an error"));
    this.child.once("error", (error) => this.fail(error));
    this.child.once("exit", (code) => this.fail(new Error(`backend exited (${code ?? "signal"})`)));
    const timer = setTimeout(() => this.fail(new Error("backend startup timed out")), 10_000);
    return this.readyPromise.finally(() => clearTimeout(timer));
  }

  async request(method: "gallery.list", params: { page_size?: number; after?: string | null } = {}): Promise<unknown> {
    if (!this.child || !this.readyPromise) throw new Error("backend is not running");
    await this.readyPromise;
    return this.send(method, params, 5_000);
  }

  async stop(): Promise<void> {
    const child = this.child;
    if (!child) return;
    this.stopping = true;
    const exited = new Promise<void>((resolveExit) => child.once("exit", () => resolveExit()));
    try {
      await this.send("shutdown", {}, 1_500);
    } catch {
      child.kill("SIGTERM");
    }
    await Promise.race([
      exited,
      new Promise<void>((resolveTimeout) => setTimeout(() => { child.kill("SIGKILL"); resolveTimeout(); }, 2_000)),
    ]);
    this.child = null;
    this.stopping = false;
  }

  private send(method: string, params: object, timeout: number): Promise<unknown> {
    const child = this.child;
    if (!child || !child.stdin.writable) return Promise.reject(new Error("backend is unavailable"));
    const id = randomUUID();
    return new Promise((resolveRequest, rejectRequest) => {
      const timer = setTimeout(() => { this.pending.delete(id); rejectRequest(new Error("backend request timed out")); }, timeout);
      this.pending.set(id, { resolve: resolveRequest, reject: rejectRequest, timer });
      child.stdin.write(JSON.stringify({ id, token: this.token, method, params }) + "\n");
    });
  }

  private consume(chunk: string): void {
    this.buffer += chunk;
    for (;;) {
      const newline = this.buffer.indexOf("\n");
      if (newline < 0) return;
      const line = this.buffer.slice(0, newline);
      this.buffer = this.buffer.slice(newline + 1);
      try { this.handle(JSON.parse(line) as ResponseMessage); } catch { this.fail(new Error("backend sent an invalid response")); }
    }
  }

  private handle(message: ResponseMessage): void {
    if (message.event === "ready") { this.markReady?.(); this.markReady = null; return; }
    if (!message.id) return;
    const pending = this.pending.get(message.id);
    if (!pending) return;
    clearTimeout(pending.timer);
    this.pending.delete(message.id);
    if (message.ok) pending.resolve(message.result);
    else pending.reject(new Error(message.error?.message ?? message.error?.code ?? "backend request failed"));
  }

  private fail(error: Error): void {
    this.failReady?.(error);
    this.failReady = null;
    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(error); }
    this.pending.clear();
    if (!this.stopping) this.emit("failure", error);
  }
}
