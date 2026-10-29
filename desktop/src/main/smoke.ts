import { BrowserWindow } from "electron";
import { resolve } from "node:path";
import type { PythonBackend } from "./backend.js";

// Exercises the production preload and renderer. Never supplies a substitute bridge.
export async function smoke(window: BrowserWindow, backend: PythonBackend): Promise<void> {
  const evaluate = <T>(code: string): Promise<T> => window.webContents.executeJavaScript(code);
  const waitFor = async (expression: string) => {
    for (let attempt = 0; attempt < 100; attempt++) {
      if (await evaluate<boolean>(expression)) return;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(`smoke timeout: ${expression}`);
  };
  await waitFor('document.querySelector(".status-panel h2")?.textContent === "Sua biblioteca está vazia"');
  const result = await evaluate<{ items: unknown[] }>('window.photoManager.listGallery({pageSize: 24})');
  if (result.items.length !== 0) throw new Error("smoke requires the default in-memory catalog");
  const exposed = await evaluate<string[]>('Object.keys(window.photoManager).sort()');
  if (exposed.join() !== 'listGallery,retryGallery') throw new Error("unexpected bridge exposure");
  if (await evaluate<boolean>('typeof process !== "undefined" || typeof require !== "undefined"')) throw new Error("Node exposed to renderer");
  for (const [width, height] of [[1180, 760], [860, 560], [760, 560], [760, 520]]) {
    window.setSize(width, height);
    await new Promise((resolve) => setTimeout(resolve, 150));
    if (await evaluate<boolean>('document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight')) throw new Error(`overflow at ${width}x${height}`);
    const privacy = await evaluate<boolean>('getComputedStyle(document.querySelector(".privacy-note span")).display !== "none"');
    if (!privacy) throw new Error("privacy text hidden from accessibility tree");
    window.webContents.debugger.attach("1.3");
    try {
      const tree = await window.webContents.debugger.sendCommand("Accessibility.getFullAXTree");
      if (!tree.nodes.some((node: { ignored: boolean; name?: { value: string } }) => !node.ignored && node.name?.value.includes("Seus originais não são alterados."))) throw new Error("privacy text absent from accessibility tree");
    } finally { window.webContents.debugger.detach(); }
    console.log(`SMOKE resize PASS: ${width}x${height}, no overflow; privacy in accessibility tree`);
  }
  await backend.stop();
  window.webContents.reload();
  await waitFor('!!document.querySelector("[role=alert] button")');
  await evaluate('document.querySelector("[role=alert] button").click()');
  await waitFor('document.querySelector(".status-panel h2")?.textContent === "Sua biblioteca está vazia"');
  const withoutPreload = new BrowserWindow({width: 760, height: 560, webPreferences: {sandbox: true, contextIsolation: true, nodeIntegration: false}});
  try {
    await withoutPreload.loadFile(resolve(import.meta.dirname, "../renderer/index.html"));
    for (let attempt = 0; attempt < 100; attempt++) {
      if (await withoutPreload.webContents.executeJavaScript('!!document.querySelector("[role=alert] button")')) break;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    if (!await withoutPreload.webContents.executeJavaScript('!!document.querySelector("[role=alert] button")')) throw new Error("missing preload produced no recovery UI");
    await withoutPreload.webContents.executeJavaScript('document.querySelector("[role=alert] button").click()');
    await new Promise((resolve) => setTimeout(resolve, 100));
    if (!await withoutPreload.webContents.executeJavaScript('!!document.querySelector("[role=alert] button")')) throw new Error("missing preload retry lost recovery UI");
  } finally { withoutPreload.destroy(); }
  console.log("SMOKE PASS: production preload → IPC → Python; resize; IPC failure; retry; missing preload");
}
