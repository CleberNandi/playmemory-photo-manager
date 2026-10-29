import { expect, it, vi } from "vitest";
import { duplicatesRequest } from "./duplicates.js";
it.each([null, [], {demo: true}, {path: "/private"}, {pageSize: 51}, {pageSize: true}, {after: 1}, {after: "x".repeat(2049)}])("rejects unsafe IPC parameters %j", async (params) => {
  const backend = {request: vi.fn()};
  expect(await duplicatesRequest(backend, "duplicates.list", params)).toEqual({status: "invalid_request"});
  expect(backend.request).not.toHaveBeenCalled();
});
it("only forwards explicit projection methods and parameters", async () => {
  const backend = {request: vi.fn().mockResolvedValue({status: "analysis_not_available"})};
  expect(await duplicatesRequest(backend, "duplicates.list", {})).toEqual({status: "analysis_not_available"});
  await duplicatesRequest(backend, "duplicates.group", {snapshotId: "s", groupKey: "g", pageSize: 24, after: "opaque"});
  expect(backend.request).toHaveBeenLastCalledWith("duplicates.group", {snapshot_id: "s", group_key: "g", page_size: 24, after: "opaque"});
});
it.each([["backend_failure", "internal_error"], ["invalid_request", "invalid_request"], ["response_too_large", "response_too_large"], ["temporarily_unavailable", "temporarily_unavailable"], [undefined, "temporarily_unavailable"]])("sanitizes %s", async (code, status) => {
  const backend = {request: vi.fn().mockRejectedValue(Object.assign(new Error("/private/token=secret"), {code}))};
  expect(await duplicatesRequest(backend, "duplicates.list", {})).toEqual({status});
});
