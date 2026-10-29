import { BrowserWindow } from "electron";
import { writeFile } from "node:fs/promises";
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
  const demo = process.env.PLAYMEMORIES_DESKTOP_DEMO === "1";
  const ready = demo ? 'document.querySelectorAll(".media-card").length === 24' : 'document.querySelector(".status-panel h2")?.textContent === "Sua biblioteca está vazia"';
  await waitFor(ready);
  const result = await evaluate<{ items: {asset_id: string}[] }>('window.photoManager.listGallery({pageSize: 24})');
  if (result.items.length !== (demo ? 24 : 0)) throw new Error("unexpected initial catalog");
  if (demo) {
    const expected: string[] = [];
    const identities = new Set<string>();
    let cursor: string | null = null;
    do {
      const page: {items: {asset_id: string; annotation: {title: string}}[]; next_cursor: string | null} = await evaluate(`window.photoManager.listGallery({pageSize: 24, after: ${JSON.stringify(cursor)}})`);
      for (const item of page.items) {
        if (identities.has(item.asset_id)) throw new Error("duplicate backend identity");
        identities.add(item.asset_id);
        expected.push(item.annotation.title);
      }
      cursor = page.next_cursor;
    } while (cursor);
    for (const count of [24, 48, 72, 73]) {
      if (count > 24) {
        await evaluate('document.querySelector(".pagination button").click()');
        await waitFor(`document.querySelectorAll(".media-card").length === ${count}`);
      }
      const visible = await evaluate<string[]>('Array.from(document.querySelectorAll(".media-card h3"), title => title.textContent)');
      if (new Set(visible).size !== count || JSON.stringify(visible) !== JSON.stringify(expected.slice(0, count))) throw new Error("renderer duplicated, lost or reordered assets");
      await waitFor(`document.querySelectorAll(".synthetic-thumbnail").length === ${count} && [...document.querySelectorAll(".synthetic-thumbnail")].every(img => img.complete && img.naturalWidth === 256 && img.naturalHeight === 160)`);
      console.log(`SMOKE thumbnails PASS: ${count} decoded PNGs`);
      console.log(`SMOKE pagination PASS: ${count} cards, exact backend order`);
    }
    if (expected.length !== 73) throw new Error("lost assets");
    await waitFor('document.querySelector(".pagination")?.textContent.includes("Fim da biblioteca")');
    await writeFile("/tmp/playmemories-d02b2-gallery.png", (await window.webContents.capturePage()).toPNG());
  }
  const exposed = await evaluate<string[]>('Object.keys(window.photoManager).sort()');
  if (exposed.join() !== 'getThumbnail,listGallery,retryGallery') throw new Error("unexpected bridge exposure");
  if (await evaluate<boolean>('typeof process !== "undefined" || typeof require !== "undefined"')) throw new Error("Node exposed to renderer");
  for (const [width, height] of [[1180, 760], [860, 560], [760, 560], [760, 520]]) {
    window.setSize(width, height);
    await new Promise((resolve) => setTimeout(resolve, 150));
    if (await evaluate<boolean>(demo ? 'document.documentElement.scrollWidth > innerWidth' : 'document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight')) throw new Error(`overflow at ${width}x${height}`);
    const privacy = await evaluate<boolean>('getComputedStyle(document.querySelector(".privacy-note span")).display !== "none"');
    if (!privacy) throw new Error("privacy text hidden from accessibility tree");
    window.webContents.debugger.attach("1.3");
    try {
      const tree = await window.webContents.debugger.sendCommand("Accessibility.getFullAXTree");
      if (!tree.nodes.some((node: { ignored: boolean; name?: { value: string } }) => !node.ignored && node.name?.value.includes("Seus originais não são alterados."))) throw new Error("privacy text absent from accessibility tree");
    } finally { window.webContents.debugger.detach(); }
    console.log(`SMOKE resize PASS: ${width}x${height}, no horizontal overflow; privacy in accessibility tree`);
  }
  await backend.stop();
  window.webContents.reload();
  await waitFor('!!document.querySelector("[role=alert] button")');
  await evaluate('document.querySelector("[role=alert] button").click()');
  await waitFor(ready);
  if (demo) await waitFor('document.querySelectorAll(".synthetic-thumbnail").length === 24 && [...document.querySelectorAll(".synthetic-thumbnail")].every(img => img.complete && img.naturalWidth === 256)');
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
  console.log("SMOKE PASS: production preload → IPC → Python; pagination/empty; resize; IPC failure; retry; missing preload");
}
