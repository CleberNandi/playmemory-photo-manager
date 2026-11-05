import { mkdtemp, mkdir, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { nativePath } from "./native-path.js";
it("canonicalizes native folder selection including a trailing slash and symlink ancestors", async () => {
  const base = await mkdtemp(join(tmpdir(), "native-path-"));
  try {
    const physical = join(base, "physical"); const alias = join(base, "alias");
    await mkdir(physical); await symlink(physical, alias);
    expect(await nativePath(`${physical}/`)).toBe(physical);
    expect(await nativePath(`${alias}/`)).toBe(physical);
    expect(await nativePath(join(alias, "new.sqlite3"), true)).toBe(join(physical, "new.sqlite3"));
    await rm(alias); await symlink(join(base, "missing"), alias);
    await expect(nativePath(alias)).rejects.toThrow("not_found");
    await expect(nativePath("relative/path")).rejects.toThrow("invalid_request");
  } finally { await rm(base, {recursive: true, force: true}); }
});
