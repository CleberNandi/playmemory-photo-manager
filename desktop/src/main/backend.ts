import { randomBytes, randomUUID } from "node:crypto";
import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { resolve } from "node:path";

type Pending = { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: NodeJS.Timeout };
type ResponseMessage = { id?: string; ok?: boolean; result?: unknown; error?: { code?: string; message?: string }; event?: string };
type BackendState = "stopped" | "starting" | "ready" | "stopping";
type SpawnBackend = typeof spawn;

export type BackendOptions = {
  spawnBackend?: SpawnBackend;
  startupTimeoutMs?: number;
  requestTimeoutMs?: number;
  shutdownTimeoutMs?: number;
  killTimeoutMs?: number;
  watchdogTimeoutMs?: number;
  platform?: NodeJS.Platform;
};

const MAX_STDERR_CHARS = 4096;

export class PythonBackend extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null;
  private readonly pending = new Map<string, Pending>();
  private token = "";
  private buffer = "";
  private stderrBuffer = "";
  private readyPromise: Promise<void> | null = null;
  private markReady: (() => void) | null = null;
  private failReady: ((error: Error) => void) | null = null;
  private state: BackendState = "stopped";
  private generation = 0;
  private repositoryRoot = "";
  private readonly spawnBackend: SpawnBackend;
  private readonly startupTimeoutMs: number;
  private readonly requestTimeoutMs: number;
  private readonly shutdownTimeoutMs: number;
  private readonly killTimeoutMs: number;
  private stopping: Promise<void> | null = null;
  private readonly watchdogTimeoutMs: number;
  private readonly platform: NodeJS.Platform;

  constructor(options: BackendOptions = {}) {
    super();
    this.spawnBackend = options.spawnBackend ?? spawn;
    this.startupTimeoutMs = options.startupTimeoutMs ?? 10_000;
    this.requestTimeoutMs = options.requestTimeoutMs ?? 5_000;
    this.shutdownTimeoutMs = options.shutdownTimeoutMs ?? 3_500;
    this.killTimeoutMs = options.killTimeoutMs ?? 2_000;
    this.watchdogTimeoutMs = options.watchdogTimeoutMs ?? 5_000;
    this.platform = options.platform ?? process.platform;
  }

  start(repositoryRoot = resolve(import.meta.dirname, "../../..")): Promise<void> {
    if (this.state !== "stopped" || this.stopping) return Promise.reject(new Error("backend is already running"));
    this.repositoryRoot = repositoryRoot;
    this.resetSession();
    this.state = "starting";
    const generation = ++this.generation;
    this.readyPromise = new Promise((resolveReady, rejectReady) => {
      this.markReady = resolveReady;
      this.failReady = rejectReady;
    });
    const child = this.spawnBackend(
      "uv",
      ["run", "--offline", "python", "-m", "playmemories_photo_manager.desktop.bridge",
        ...(process.env.PLAYMEMORIES_DESKTOP_DEMO === "1" ? ["--demo"] : [])],
      {
        cwd: repositoryRoot,
        detached: this.platform !== "win32",
        env: { ...process.env, PLAYMEMORIES_BRIDGE_TOKEN: this.token },
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    this.child = child;
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => this.consume(chunk, generation));
    child.stderr.on("data", (chunk: string) => this.consumeStderr(chunk, generation));
    child.once("error", (error) => this.fail(error, generation));
    child.once("exit", (code, signal) => {
      const expected = this.state === "stopping";
      this.fail(new Error(`backend exited (${code ?? signal ?? "unknown"})`), generation, expected);
    });
    const timer = setTimeout(() => this.fail(new Error("backend startup timed out"), generation), this.startupTimeoutMs);
    return this.readyPromise.finally(() => clearTimeout(timer));
  }

  async restart(): Promise<void> {
    await this.stop();
    await this.start(this.repositoryRoot || undefined);
  }

  async request(method: "annotation.favorite" | "ingestion.apply" | "ingestion.application_status" | "ingestion.select_root" | "ingestion.prepare" | "ingestion.status" | "ingestion.cancel" | "ingestion.page" | "library.state" | "library.create" | "library.open" | "library.close" | "gallery.list" | "calendar.summary" | "preview.get" | "thumbnail.get" | "asset.details" | "duplicates.list" | "duplicates.group", params: Record<string, unknown> = {}): Promise<unknown> {
    if (!this.child || !this.readyPromise || (this.state === "stopped" || this.state === "stopping")) throw new Error("backend is not running");
    await this.readyPromise;
    return this.send(method, params, this.requestTimeoutMs);
  }

  stop(): Promise<void> {
    if (this.stopping) return this.stopping;
    this.stopping = this.stopOwned().finally(() => { this.stopping = null; });
    return this.stopping;
  }

  private released(child: ChildProcessWithoutNullStreams): boolean {
    if (!child.pid) return true;
    if (child.exitCode === null && child.signalCode === null) return false;
    if (this.platform === "win32") return true;
    try { process.kill(-child.pid, 0); return false; }
    catch (error) { return (error as NodeJS.ErrnoException).code === "ESRCH"; }
  }

  private async waitReleased(child: ChildProcessWithoutNullStreams, timeout: number): Promise<boolean> {
    const deadline = performance.now() + Math.max(0, timeout);
    while (!this.released(child) && performance.now() < deadline) {
      await new Promise<void>((done) => setTimeout(done, Math.min(10, Math.max(1, deadline - performance.now()))));
    }
    return this.released(child);
  }

  private async stopOwned(): Promise<void> {
    const child = this.child;
    if (!child) { this.clearSession(); return; }
    this.state = "stopping";
    const started = performance.now();
    let killed = false;
    const kill = () => { if (!killed && !this.released(child)) { killed = true; this.signal(child, "SIGKILL"); } };
    const watchdog = setTimeout(kill, this.watchdogTimeoutMs);
    try {
      try {
        if (this.readyPromise) {
          let readyTimer: NodeJS.Timeout | undefined;
          try {
            await Promise.race([this.readyPromise, new Promise<void>((_resolve, reject) => {
              readyTimer = setTimeout(() => reject(new Error("backend cleanup pending")), this.shutdownTimeoutMs);
            })]);
          } finally { if (readyTimer) clearTimeout(readyTimer); }
        }
        await this.send("shutdown", {}, Math.max(1, this.shutdownTimeoutMs - (performance.now() - started)));
      } catch { /* Unknown outcome still requires confirmed process/group cleanup. */ }
      if (!(await this.waitReleased(child, this.shutdownTimeoutMs - (performance.now() - started)))) {
        this.signal(child, "SIGTERM");
        if (!(await this.waitReleased(child, this.watchdogTimeoutMs - (performance.now() - started)))) {
          kill();
          await this.waitReleased(child, this.killTimeoutMs);
        }
      }
      if (!this.released(child)) throw new Error("backend cleanup pending");
      if (this.child === child) this.clearSession();
    } finally { clearTimeout(watchdog); }
  }

  private resetSession(): void {
    this.token = randomBytes(32).toString("hex");
    this.buffer = "";
    this.stderrBuffer = "";
  }

  private clearSession(): void {
    this.child = null;
    this.readyPromise = null;
    this.markReady = null;
    this.failReady = null;
    this.state = "stopped";
    this.buffer = "";
    this.token = "";
  }

  private signal(child: ChildProcessWithoutNullStreams, signal: NodeJS.Signals): void {
    // Never signal a numeric group after its leader was reaped: that ID can be reused.
    if (child.exitCode !== null || child.signalCode !== null) return;
    if (this.platform !== "win32" && child.pid) {
      try { process.kill(-child.pid, signal); return; } catch { /* Process group may already be gone. */ }
    }
    child.kill(signal);
  }

  private send(method: string, params: object, timeout: number): Promise<unknown> {
    const child = this.child;
    if (!child || !child.stdin.writable) return Promise.reject(new Error("backend is unavailable"));
    if (this.pending.size >= 16) return Promise.reject(Object.assign(new Error("busy"), {code:"busy"}));
    const id = randomUUID();
    const payload = JSON.stringify({id, token:this.token, method, params}) + "\n";
    if (Buffer.byteLength(payload, "utf8") > 64 * 1024) return Promise.reject(Object.assign(new Error("invalid_request"), {code:"invalid_request"}));
    return new Promise((resolveRequest, rejectRequest) => {
      const timer = setTimeout(() => { this.pending.delete(id); rejectRequest(new Error("backend request timed out")); }, timeout);
      this.pending.set(id, { resolve: resolveRequest, reject: rejectRequest, timer });
      child.stdin.write(payload, (error) => {
        if (!error) return;
        clearTimeout(timer);
        this.pending.delete(id);
        rejectRequest(new Error("backend request could not be sent"));
      });
    });
  }

  private consume(chunk: string, generation: number): void {
    if (generation !== this.generation) return;
    this.buffer += chunk;
    if (this.buffer.length > 256 * 1024) { this.fail(new Error("backend response too large"), generation); return; }
    for (;;) {
      const newline = this.buffer.indexOf("\n");
      if (newline < 0) return;
      const line = this.buffer.slice(0, newline);
      this.buffer = this.buffer.slice(newline + 1);
      try { this.handle(JSON.parse(line) as ResponseMessage); } catch { this.fail(new Error("backend sent an invalid response"), generation); }
    }
  }

  private consumeStderr(chunk: string, generation: number): void {
    if (generation !== this.generation || this.stderrBuffer.length >= MAX_STDERR_CHARS) return;
    this.stderrBuffer += chunk.slice(0, MAX_STDERR_CHARS - this.stderrBuffer.length);
    for (;;) {
      const newline = this.stderrBuffer.indexOf("\n");
      if (newline < 0) return;
      const line = this.stderrBuffer.slice(0, newline);
      this.stderrBuffer = this.stderrBuffer.slice(newline + 1);
      const diagnostic = sanitizeDiagnostic(line);
      if (diagnostic) this.emit("diagnostic", diagnostic);
    }
  }

  private handle(message: ResponseMessage): void {
    if (message.event === "ready") {
      if (this.state !== "starting") return;
      this.state = "ready";
      this.markReady?.();
      this.markReady = null;
      this.failReady = null;
      return;
    }
    if (!message.id) return;
    const pending = this.pending.get(message.id);
    if (!pending) return;
    clearTimeout(pending.timer);
    this.pending.delete(message.id);
    if (message.ok) pending.resolve(message.result);
    else pending.reject(Object.assign(new Error(message.error?.message ?? "backend request failed"), {code: message.error?.code}));
  }

  private fail(error: Error, generation: number, expected = false): void {
    if (generation !== this.generation) return;
    const child = this.child;
    this.failReady?.(error);
    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(error); }
    this.pending.clear();
    if (!child || this.released(child)) this.clearSession();
    else {
      this.state = "stopping";
      if (!expected) this.signal(child, "SIGTERM");
      const killTimer = setTimeout(() => this.signal(child, "SIGKILL"), this.killTimeoutMs);
      killTimer.unref();
      const cleanup = setInterval(() => {
        if (!this.released(child)) return;
        clearTimeout(killTimer);
        clearInterval(cleanup);
        if (this.child === child) this.clearSession();
      }, 10);
      cleanup.unref();
    }
    if (!expected) this.emit("failure", error);
  }
}

export function sanitizeDiagnostic(line: string): string | null {
  const printable = [...line]
    .map((character) => {
      const code = character.charCodeAt(0);
      return code < 32 || code === 127 ? " " : character;
    })
    .join("");
  const cleaned = printable
    .replace(/(token|secret|password|authorization)\s*[=:]\s*\S+/gi, "$1=[redacted]")
    .replace(/(?:file:\/\/|\/)[^\s]+/g, "[path]")
    .trim()
    .slice(0, 512);
  return cleaned ? `backend stderr: ${cleaned}` : null;
}
