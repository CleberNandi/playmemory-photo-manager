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
  private readonly platform: NodeJS.Platform;

  constructor(options: BackendOptions = {}) {
    super();
    this.spawnBackend = options.spawnBackend ?? spawn;
    this.startupTimeoutMs = options.startupTimeoutMs ?? 10_000;
    this.requestTimeoutMs = options.requestTimeoutMs ?? 5_000;
    this.shutdownTimeoutMs = options.shutdownTimeoutMs ?? 1_500;
    this.killTimeoutMs = options.killTimeoutMs ?? 2_000;
    this.platform = options.platform ?? process.platform;
  }

  start(repositoryRoot = resolve(import.meta.dirname, "../../..")): Promise<void> {
    if (this.state !== "stopped") return Promise.reject(new Error("backend is already running"));
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

  async request(method: "library.state" | "library.create" | "library.open" | "library.close" | "gallery.list" | "thumbnail.get" | "asset.details" | "duplicates.list" | "duplicates.group", params: Record<string, unknown> = {}): Promise<unknown> {
    if (!this.child || !this.readyPromise || this.state === "stopped") throw new Error("backend is not running");
    await this.readyPromise;
    return this.send(method, params, this.requestTimeoutMs);
  }

  async stop(): Promise<void> {
    const child = this.child;
    if (!child) { this.clearSession(); return; }
    this.state = "stopping";
    const exited = new Promise<void>((resolveExit) => child.once("exit", () => resolveExit()));
    try {
      if (this.readyPromise) await this.readyPromise;
      await this.send("shutdown", {}, this.shutdownTimeoutMs);
    } catch { /* Continue with signal escalation. */ }
    if (!(await this.waitFor(exited, this.shutdownTimeoutMs))) {
      this.signal(child, "SIGTERM");
    }
    if (child.exitCode === null && child.signalCode === null && !(await this.waitFor(exited, this.killTimeoutMs))) {
      this.signal(child, "SIGKILL");
      await this.waitFor(exited, this.killTimeoutMs);
    }
    if (this.child === child) this.clearSession();
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

  private waitFor(exited: Promise<void>, timeoutMs: number): Promise<boolean> {
    return new Promise((resolveWait) => {
      const timer = setTimeout(() => resolveWait(false), timeoutMs);
      exited.then(() => { clearTimeout(timer); resolveWait(true); });
    });
  }

  private signal(child: ChildProcessWithoutNullStreams, signal: NodeJS.Signals): void {
    if (this.platform !== "win32" && child.pid) {
      try { process.kill(-child.pid, signal); return; } catch { /* Process group may already be gone. */ }
    }
    child.kill(signal);
  }

  private send(method: string, params: object, timeout: number): Promise<unknown> {
    const child = this.child;
    if (!child || !child.stdin.writable) return Promise.reject(new Error("backend is unavailable"));
    const id = randomUUID();
    return new Promise((resolveRequest, rejectRequest) => {
      const timer = setTimeout(() => { this.pending.delete(id); rejectRequest(new Error("backend request timed out")); }, timeout);
      this.pending.set(id, { resolve: resolveRequest, reject: rejectRequest, timer });
      child.stdin.write(JSON.stringify({ id, token: this.token, method, params }) + "\n", (error) => {
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
    this.clearSession();
    if (child && !expected && child.exitCode === null && child.signalCode === null) {
      this.signal(child, "SIGTERM");
      const killTimer = setTimeout(() => {
        if (child.exitCode === null && child.signalCode === null) this.signal(child, "SIGKILL");
      }, this.killTimeoutMs);
      killTimer.unref();
      child.once("exit", () => clearTimeout(killTimer));
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
