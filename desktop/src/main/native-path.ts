import { realpath } from "node:fs/promises";
import { basename, dirname, isAbsolute, join } from "node:path";

// Only main calls this with a native-dialog selection. Python still validates the
// physical destination independently with descriptors and O_NOFOLLOW.
export async function nativePath(selected: string, create = false): Promise<string> {
  if (!isAbsolute(selected) || selected.length > 4096 || selected.includes("\0")) throw Object.assign(new Error("invalid_request"), {code: "invalid_request"});
  try {
    return create ? join(await realpath(dirname(selected)), basename(selected)) : await realpath(selected);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    throw Object.assign(new Error(code === "EACCES" ? "permission_denied" : code === "ENOENT" ? "not_found" : "unsafe_location"), {code: code === "EACCES" ? "permission_denied" : code === "ENOENT" ? "not_found" : "unsafe_location"});
  }
}
