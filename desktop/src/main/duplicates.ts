import type { PythonBackend } from "./backend.js";

// Validate duplicate IPC channels independently of renderer/preload types. No mode or path input.
export async function duplicatesRequest(backend: Pick<PythonBackend, "request">, method: "duplicates.start" | "duplicates.list" | "duplicates.group" | "duplicates.decide" | "duplicates.remove", input: unknown): Promise<unknown> {
  if (!input || typeof input !== "object" || Array.isArray(input)) return {status: "invalid_request"};
  const p = input as Record<string, unknown>;
  if (method === "duplicates.remove") {
    if (Object.keys(p).sort().join() !== "groupKey,removeLocationId,snapshotId" ||
        typeof p.snapshotId !== "string" || p.snapshotId.length > 100 || !p.snapshotId ||
        typeof p.groupKey !== "string" || p.groupKey.length > 100 || !p.groupKey ||
        typeof p.removeLocationId !== "string" || !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(p.removeLocationId)) return {status: "invalid_request"};
    try {
      return await backend.request("duplicates.remove", {
        snapshot_id: p.snapshotId, group_key: p.groupKey, remove_location_id: p.removeLocationId,
      });
    } catch (error) {
      const code = (error as {code?: string}).code;
      return {status: code === "backend_failure" ? "internal_error" : code === "invalid_request" ? "invalid_request" : code === "response_too_large" ? "response_too_large" : "temporarily_unavailable"};
    }
  }
  if (method === "duplicates.decide") {
    if (Object.keys(p).sort().join() !== "groupKey,keepLocationId,reason,snapshotId" ||
        typeof p.snapshotId !== "string" || p.snapshotId.length > 100 || !p.snapshotId ||
        typeof p.groupKey !== "string" || p.groupKey.length > 100 || !p.groupKey ||
        typeof p.keepLocationId !== "string" || !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(p.keepLocationId) ||
        typeof p.reason !== "string" || !p.reason.trim() || p.reason.length > 200 || p.reason.includes("\0")) return {status: "invalid_request"};
    try {
      return await backend.request("duplicates.decide", {
        snapshot_id: p.snapshotId, group_key: p.groupKey, keep_location_id: p.keepLocationId, reason: p.reason,
      });
    } catch (error) {
      const code = (error as {code?: string}).code;
      return {status: code === "backend_failure" ? "internal_error" : code === "invalid_request" ? "invalid_request" : code === "response_too_large" ? "response_too_large" : "temporarily_unavailable"};
    }
  }
  const group = method === "duplicates.group";
  const allowed = method === "duplicates.start" ? [] : group ? ["pageSize", "after", "snapshotId", "groupKey"] : ["pageSize", "after"];
  if (Object.keys(p).some((key) => !allowed.includes(key)) ||
      (p.pageSize !== undefined && (!Number.isInteger(p.pageSize) || (p.pageSize as number) < 1 || (p.pageSize as number) > 50)) ||
      (p.after !== undefined && p.after !== null && (typeof p.after !== "string" || p.after.length > 2048)) ||
      (group && (typeof p.snapshotId !== "string" || p.snapshotId.length > 100 || typeof p.groupKey !== "string" || p.groupKey.length > 100))) return {status: "invalid_request"};
  try {
    return await backend.request(method, method === "duplicates.start" ? {} : {page_size: p.pageSize as number | undefined, after: p.after as string | null | undefined,
      ...(group ? {snapshot_id: p.snapshotId as string, group_key: p.groupKey as string} : {})});
  } catch (error) {
    const code = (error as {code?: string}).code;
    return {status: code === "backend_failure" ? "internal_error" : code === "invalid_request" ? "invalid_request" : code === "response_too_large" ? "response_too_large" : "temporarily_unavailable"};
  }
}
