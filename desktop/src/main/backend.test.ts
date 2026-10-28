import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { describe, expect, it, vi } from "vitest";
import { PythonBackend, sanitizeDiagnostic } from "./backend.js";

class FakeChild extends EventEmitter {
  readonly stdin = new PassThrough(); readonly stdout = new PassThrough(); readonly stderr = new PassThrough();
  readonly pid = 1234; exitCode: number | null = null; signalCode: NodeJS.Signals | null = null;
  readonly signals: NodeJS.Signals[] = [];
  constructor(private readonly autoExit = true) {
    super();
    this.stdin.setEncoding("utf8");
    this.stdin.on("data", (chunk: string) => {
      for (const line of chunk.trim().split("\n")) {
        const request = JSON.parse(line) as { id: string; method: string };
        if (request.method === "shutdown") {
          this.stdout.write(JSON.stringify({ id: request.id, ok: true, result: { accepted: true } }) + "\n");
          if (this.autoExit) queueMicrotask(() => this.exit(0));
        } else this.stdout.write(JSON.stringify({ id: request.id, ok: true, result: { items: [] } }) + "\n");
      }
    });
  }
  ready(): void { this.stdout.write('{"event":"ready","protocol":1}\n'); }
  exit(code: number | null, signal: NodeJS.Signals | null = null): void { this.exitCode = code; this.signalCode = signal; this.emit("exit", code, signal); }
  kill(signal: NodeJS.Signals): boolean { this.signals.push(signal); if (this.autoExit) queueMicrotask(() => this.exit(null, signal)); return true; }
}

const spawnSequence = (...children: FakeChild[]) => vi.fn(() => children.shift() as never);

describe("PythonBackend lifecycle", () => {
  it("fails closed before startup and allows idempotent shutdown", async () => {
    const backend = new PythonBackend();
    await expect(backend.request("gallery.list")).rejects.toThrow("not running");
    await expect(backend.stop()).resolves.toBeUndefined();
  });

  it("uses uv offline and shuts down normally", async () => {
    const child = new FakeChild(); const spawnBackend = spawnSequence(child);
    const backend = new PythonBackend({ spawnBackend, platform: "win32" });
    const started = backend.start("/synthetic/repository"); child.ready(); await started;
    await expect(backend.request("gallery.list")).resolves.toEqual({ items: [] });
    await backend.stop();
    expect(spawnBackend).toHaveBeenCalledWith("uv", ["run", "--offline", "python", "-m", "playmemories_photo_manager.desktop.bridge"], expect.objectContaining({ cwd: "/synthetic/repository", detached: false }));
    expect(child.signals).toEqual([]);
    await expect(backend.request("gallery.list")).rejects.toThrow("not running");
  });

  it("terminates a startup timeout and can start a fresh generation", async () => {
    const first = new FakeChild(); const second = new FakeChild();
    const backend = new PythonBackend({ spawnBackend: spawnSequence(first, second), platform: "win32", startupTimeoutMs: 5 });
    await expect(backend.start("/synthetic/repository")).rejects.toThrow("startup timed out");
    expect(first.signals).toEqual(["SIGTERM"]);
    const restarted = backend.start("/synthetic/repository"); second.ready(); await expect(restarted).resolves.toBeUndefined();
    await backend.stop();
  });

  it("clears stale state after a crash and allows controlled restart", async () => {
    const first = new FakeChild(); const second = new FakeChild();
    const backend = new PythonBackend({ spawnBackend: spawnSequence(first, second), platform: "win32" });
    backend.on("failure", () => undefined);
    const started = backend.start("/synthetic/repository"); first.ready(); await started; first.exit(7);
    await expect(backend.request("gallery.list")).rejects.toThrow("not running");
    const restarted = backend.restart(); second.ready(); await restarted;
    await expect(backend.request("gallery.list")).resolves.toEqual({ items: [] }); await backend.stop();
  });

  it("escalates from SIGTERM to SIGKILL when shutdown is stuck", async () => {
    vi.useFakeTimers();
    try {
      const child = new FakeChild(false);
      const backend = new PythonBackend({ spawnBackend: spawnSequence(child), platform: "win32", shutdownTimeoutMs: 5, killTimeoutMs: 5 });
      const started = backend.start(); child.ready(); await started;
      const stopping = backend.stop(); await vi.advanceTimersByTimeAsync(20); child.exit(null, "SIGKILL"); await stopping;
      expect(child.signals).toEqual(["SIGTERM", "SIGKILL"]);
    } finally { vi.useRealTimers(); }
  });
});

describe("backend diagnostics", () => {
  it("keeps bounded context while redacting secrets and paths", () => {
    expect(sanitizeDiagnostic("token=top-secret failed at /home/user/private/catalog.sqlite")).toBe("backend stderr: token=[redacted] failed at [path]");
    expect(sanitizeDiagnostic("x".repeat(700))?.length).toBeLessThanOrEqual(528);
  });
});
