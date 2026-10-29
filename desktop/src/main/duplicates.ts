import type { PythonBackend } from "./backend.js";

// Validate both IPC channels independently of renderer/preload types. No mode or path input.
export async function duplicatesRequest(backend: Pick<PythonBackend, "request">, method: "duplicates.list" | "duplicates.group", input: unknown): Promise<unknown> {
  if (!input || typeof input !== "object" || Array.isArray(input)) return {status: "invalid_request"};
  const p = input as Record<string, unknown>;
  const group = method === "duplicates.group";
  const allowed = group ? ["pageSize", "after", "snapshotId", "groupKey"] : ["pageSize", "after"];
  if (Object.keys(p).some((key) => !allowed.includes(key)) ||
      (p.pageSize !== undefined && (!Number.isInteger(p.pageSize) || (p.pageSize as number) < 1 || (p.pageSize as number) > 50)) ||
      (p.after !== undefined && p.after !== null && (typeof p.after !== "string" || p.after.length > 2048)) ||
      (group && (typeof p.snapshotId !== "string" || p.snapshotId.length > 100 || typeof p.groupKey !== "string" || p.groupKey.length > 100))) return {status: "invalid_request"};
  try {
    return await backend.request(method, {page_size: p.pageSize as number | undefined, after: p.after as string | null | undefined,
      ...(group ? {snapshot_id: p.snapshotId as string, group_key: p.groupKey as string} : {})});
  } catch (error) {
    const code = (error as {code?: string}).code;
    return {status: code === "backend_failure" ? "internal_error" : code === "invalid_request" ? "invalid_request" : code === "response_too_large" ? "response_too_large" : "temporarily_unavailable"};
  }
}
