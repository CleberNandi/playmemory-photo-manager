// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MediaDevicesPanel } from "./MediaDevicesPanel";

let root: Root | null = null;
let container: HTMLDivElement;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root?.unmount());
  root = null;
  container.remove();
  delete (window as { photoManager?: unknown }).photoManager;
});

it("lists connected devices and imports media from a device or folder", async () => {
  const listMediaDevices = vi.fn(async () => ({
    status: "ready" as const,
    devices: [{ id: "storage:sdb", name: "Sony SD Card", kind: "storage" as const }],
    total_count: 1,
  }));
  const importMediaFromDevice = vi.fn(async () => ({
    status: "ready" as const,
    copiedCount: 3,
    skippedCount: 1,
    excludedCount: 0,
    catalogedCount: 3,
  }));
  const onImported = vi.fn();
  (window as { photoManager?: unknown }).photoManager = {
    listMediaDevices,
    importMediaFromDevice,
  };

  await act(async () => {
    root!.render(<MediaDevicesPanel onImported={onImported} />);
  });

  const detectButton = Array.from(container.querySelectorAll("button")).find(
    (btn) => btn.textContent === "Detectar dispositivos",
  )!;
  await act(async () => {
    detectButton.click();
  });
  expect(listMediaDevices).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain("Sony SD Card");

  const deviceImportButton = Array.from(container.querySelectorAll("button")).find(
    (btn) => btn.textContent === "Importar…",
  )!;
  await act(async () => {
    deviceImportButton.click();
  });
  expect(importMediaFromDevice).toHaveBeenCalledWith("storage:sdb");
  expect(onImported).toHaveBeenCalledWith({
    status: "ready",
    copiedCount: 3,
    skippedCount: 1,
    excludedCount: 0,
    catalogedCount: 3,
  });
  expect(container.textContent).toContain("3 arquivo(s) copiado(s) · 3 catalogado(s).");

  const folderImportButton = Array.from(container.querySelectorAll("button")).find(
    (btn) => btn.textContent === "Importar de pasta/câmera…",
  )!;
  importMediaFromDevice.mockResolvedValueOnce({ status: "cancelled" } as never);
  await act(async () => {
    folderImportButton.click();
  });
  expect(importMediaFromDevice).toHaveBeenLastCalledWith(null);
  expect(container.textContent).toContain("Importação cancelada.");
});
