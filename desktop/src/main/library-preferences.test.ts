import { mkdtemp, rm, readFile, stat, readdir, symlink, writeFile, chmod } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { afterEach, it, expect } from "vitest";
import { LibraryPreferences, emptyPreference } from "./library-preferences.js";

const folders: string[] = [];
async function folder() { const path = await mkdtemp(join(tmpdir(), "pm-preferences-")); folders.push(path); return path; }
afterEach(async () => { for (const path of folders.splice(0)) await rm(path, {recursive: true, force: true}); });

it("does not create missing preferences on read and atomically persists a restricted versioned selection", async () => {
  const path = await folder(); const store = new LibraryPreferences(path);
  expect(await store.read()).toEqual(emptyPreference()); expect(await readdir(path)).toEqual([]);
  const value = {version: 1 as const, reopen: true, last: {path: "/synthetic/catalog", handle: randomUUID()}};
  await store.write(value);
  expect(await store.read()).toEqual(value);
  expect((await stat(join(path, "library-state/selection.json"))).mode & 0o777).toBe(0o600);
  expect((await stat(join(path, "library-state"))).mode & 0o777).toBe(0o700);
  await store.write(emptyPreference());
  expect(await readdir(join(path, "library-state"))).toEqual(["selection.json"]);
});

it("rejects preference symlinks without touching the target", async () => {
  const path = await folder(); const store = new LibraryPreferences(path);
  await store.write(emptyPreference());
  const file = join(path, "library-state/selection.json");
  const target = join(path, "target"); await writeFile(target, "unchanged");
  await rm(file); await symlink(target, file);
  await expect(store.read()).rejects.toThrow("preference_invalid");
  await expect(store.write(emptyPreference())).rejects.toThrow();
  expect(await readFile(target, "utf8")).toBe("unchanged");
});

it("rejects extra keys, oversized records and broadly readable metadata", async () => {
  const path = await folder(); const store = new LibraryPreferences(path);
  await store.write(emptyPreference()); const file = join(path, "library-state/selection.json");
  for (const data of ['{"version":1,"last":null,"reopen":false,"token":"bad"}', "x".repeat(16385)]) {
    await writeFile(file, data); await expect(store.read()).rejects.toThrow("preference_invalid");
  }
  await store.write(emptyPreference()); await chmod(file, 0o644);
  await expect(store.read()).rejects.toThrow("preference_invalid");
});
