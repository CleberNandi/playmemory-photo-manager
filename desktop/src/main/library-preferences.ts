import { constants } from "node:fs";
import { lstat, mkdir, open, rename, unlink } from "node:fs/promises";
import { dirname, isAbsolute, join, normalize, parse, relative } from "node:path";
import { randomUUID } from "node:crypto";

export interface LibraryPreference { version: 1; reopen: boolean; last: { path: string; handle: string } | null }
export const emptyPreference = (): LibraryPreference => ({ version: 1, reopen: false, last: null });
export const canonicalId = (id: unknown): id is string => typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id);
export function validPath(path: unknown): path is string {
  return typeof path === "string" && path.length > 0 && path.length <= 4096 && !path.includes("\0") && isAbsolute(path) && normalize(path) === path;
}
function valid(value: unknown): value is LibraryPreference {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const p = value as LibraryPreference;
  return Object.keys(p).sort().join() === "last,reopen,version" && p.version === 1 && typeof p.reopen === "boolean" &&
    (p.last === null || (typeof p.last === "object" && !Array.isArray(p.last) && Object.keys(p.last).sort().join() === "handle,path" && validPath(p.last.path) && canonicalId(p.last.handle)));
}

// Private shell metadata only. No selected media is enumerated. Same-user hostile
// processes are outside the isolation guarantee, as with the library adapter.
export class LibraryPreferences {
  private readonly folder: string;
  private readonly file: string;
  constructor(userData: string) {
    this.folder = join(userData, "library-state");
    this.file = join(this.folder, "selection.json");
  }
  private async directory(create: boolean): Promise<void> {
    const root = parse(this.folder).root;
    let current = root;
    for (const part of relative(root, this.folder).split("/")) {
      current = join(current, part);
      let info;
      try { info = await lstat(current); }
      catch (error) {
        if (!create || (error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
        await mkdir(current, {mode: 0o700});
        info = await lstat(current);
      }
      if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("unsafe preferences");
      const owner = process.getuid?.();
      if ((info.uid !== 0 && info.uid !== owner) || ((info.mode & 0o022) !== 0 && (info.mode & 0o1000) === 0)) throw new Error("unsafe preferences");
      if (current === this.folder && ((info.mode & 0o077) !== 0 || info.uid !== process.getuid?.())) throw new Error("unsafe preferences");
    }
  }
  async read(): Promise<LibraryPreference> {
    try {
      await this.directory(false);
      const file = await open(this.file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
      try {
        const info = await file.stat();
        if (!info.isFile() || info.nlink !== 1 || info.size > 16384 || info.uid !== process.getuid?.() || (info.mode & 0o077) !== 0) throw new Error("unsafe preferences");
        const buffer = Buffer.alloc(16385);
        const {bytesRead} = await file.read(buffer, 0, buffer.length, 0);
        if (bytesRead > 16384) throw new Error("invalid preferences");
        const value: unknown = JSON.parse(buffer.subarray(0, bytesRead).toString("utf8"));
        if (!valid(value)) throw new Error("invalid preferences");
        return value;
      } finally { await file.close(); }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return emptyPreference();
      throw new Error("preference_invalid", {cause: error});
    }
  }
  async write(value: LibraryPreference): Promise<void> {
    if (!valid(value)) throw new Error("preference_invalid");
    await this.directory(true);
    try {
      const old = await lstat(this.file);
      if (!old.isFile() || old.nlink !== 1 || old.uid !== process.getuid?.()) throw new Error("unsafe preferences");
    } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
    const temporary = join(dirname(this.file), `selection-${randomUUID()}.tmp`);
    const file = await open(temporary, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
    try {
      try { await file.writeFile(JSON.stringify(value), "utf8"); await file.sync(); }
      finally { await file.close(); }
      await rename(temporary, this.file);
    } catch (error) { await unlink(temporary).catch(() => undefined); throw error; }
  }
}
