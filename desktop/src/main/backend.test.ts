import { describe, expect, it } from "vitest";
import { PythonBackend } from "./backend.js";

describe("PythonBackend lifecycle", () => {
  it("fails closed before startup", async () => {
    const backend = new PythonBackend();
    await expect(backend.request("gallery.list")).rejects.toThrow("not running");
  });

  it("allows idempotent shutdown before startup", async () => {
    const backend = new PythonBackend();
    await expect(backend.stop()).resolves.toBeUndefined();
  });
});
