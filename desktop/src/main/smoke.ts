import { BrowserWindow } from "electron";
import { readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import type { PythonBackend } from "./backend.js";

// Exercises the production preload and renderer. Never supplies a substitute bridge.
export async function smoke(window: BrowserWindow, backend: PythonBackend, mediaRoot?: string): Promise<void> {
  const evaluate = <T>(code: string): Promise<T> => window.webContents.executeJavaScript(code);
  const waitFor = async (expression: string) => {
    for (let attempt = 0; attempt < 100; attempt++) {
      if (await evaluate<boolean>(expression)) return;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(`smoke timeout: ${expression}`);
  };
  const demo = process.env.PLAYMEMORIES_DESKTOP_DEMO === "1";
  if (!demo) { await smokeLibraries(window, backend, mediaRoot); return; }
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
    const toolbarTop = await evaluate<number>('document.querySelector(".view-toolbar").getBoundingClientRect().top');
    const cardTop = await evaluate<number>('document.querySelector(".media-card").getBoundingClientRect().top');
    await evaluate('document.querySelector(".workspace").scrollTop = 350');
    await new Promise((resolve) => setTimeout(resolve, 50));
    if (!await evaluate<boolean>(`document.querySelector(".workspace").scrollTop > 0 && Math.abs(document.querySelector(".view-toolbar").getBoundingClientRect().top - ${toolbarTop}) < 1 && document.querySelector(".media-card").getBoundingClientRect().top < ${cardTop}`)) throw new Error("view toolbar scrolled away with gallery");
    await evaluate('document.querySelector(".workspace").scrollTop = 0');
    console.log("SMOKE toolbar PASS: controls remain pinned while cards scroll");
    window.focus();
    window.webContents.focus();
    await evaluate('document.querySelector(".card-select").focus()');
    await new Promise((resolve) => setTimeout(resolve, 150));
    window.webContents.sendInputEvent({type: "keyDown", keyCode: "Enter"});
    window.webContents.sendInputEvent({type: "char", keyCode: "\r"});
    window.webContents.sendInputEvent({type: "keyUp", keyCode: "Enter"});
    await waitFor('!!document.querySelector(".asset-details")');
    await waitFor('!!document.querySelector(".asset-details dl")');
    if (!await evaluate('document.querySelector(".asset-details").textContent.includes("Metadata não extraída")')) throw new Error("missing metadata state");
    await writeFile("/tmp/playmemories-d02c-details.png", (await window.webContents.capturePage()).toPNG());
    window.webContents.sendInputEvent({type: "keyDown", keyCode: "Escape"});
    window.webContents.sendInputEvent({type: "keyUp", keyCode: "Escape"});
    await waitFor('!document.querySelector(".asset-details")');
    if (!await evaluate('document.activeElement.classList.contains("card-select")')) throw new Error("details focus not restored");
    console.log("SMOKE details PASS: real DTO, absence state, close and focus restoration");
    if (expected.length !== 73) throw new Error("lost assets");
    await waitFor('document.querySelector(".pagination")?.textContent.includes("Fim da biblioteca")');
    await writeFile("/tmp/playmemories-d02b2-gallery.png", (await window.webContents.capturePage()).toPNG());
  }
  const exposed = await evaluate<string[]>('Object.keys(window.photoManager).sort()');
  if (exposed.join() !== 'applyCataloging,cancelPreparation,chooseCreateLibrary,chooseMediaRoot,chooseOpenLibrary,closeLibrary,forgetLibrary,getAssetDetails,getCalendar,getCatalogingApplicationStatus,getDuplicateGroup,getLibraryState,getPreparationStatus,getPreview,getThumbnail,listCatalogingCandidates,listDuplicates,listGallery,onBackendReset,prepareCataloging,retryGallery,setFavorite,setReopenLibrary') throw new Error("unexpected bridge exposure");
  const invalidDetails = await evaluate<{status: string}>('window.photoManager.getAssetDetails("../invalid")');
  const absentDetails = await evaluate<{status: string}>('window.photoManager.getAssetDetails("00000000-0000-0000-0000-000000000000")');
  if (invalidDetails.status !== "invalid_request" || absentDetails.status !== "not_found") throw new Error("details error contract failed");
  if (await evaluate<boolean>('typeof process !== "undefined" || typeof require !== "undefined"')) throw new Error("Node exposed to renderer");
  for (const [width, height] of [[1180, 760], [860, 560], [760, 560], [760, 520]]) {
    window.setSize(width, height);
    await new Promise((resolve) => setTimeout(resolve, 150));
    if (demo) {
      await evaluate('document.querySelector(".card-select").click()');
      await waitFor('!!document.querySelector(".asset-details dl")');
    }
    if (await evaluate<boolean>(demo ? 'document.documentElement.scrollWidth > innerWidth' : 'document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight')) throw new Error(`overflow at ${width}x${height}`);
    const privacy = await evaluate<boolean>('getComputedStyle(document.querySelector(".privacy-note span")).display !== "none"');
    if (!privacy) throw new Error("privacy text hidden from accessibility tree");
    window.webContents.debugger.attach("1.3");
    try {
      const tree = await window.webContents.debugger.sendCommand("Accessibility.getFullAXTree");
      if (!tree.nodes.some((node: { ignored: boolean; name?: { value: string } }) => !node.ignored && node.name?.value.includes("Seus originais não são alterados."))) throw new Error("privacy text absent from accessibility tree");
    } finally { window.webContents.debugger.detach(); }
    if (demo) await evaluate('document.querySelector(".asset-details button").click()');
    console.log(`SMOKE resize PASS: ${width}x${height}, no horizontal overflow; privacy in accessibility tree`);
  }
  if (demo) {
    await backend.stop();
    await evaluate('document.querySelector(".card-select").click()');
    await waitFor('!!document.querySelector(".asset-details [role=alert]")');
    await evaluate('document.querySelector(".asset-details [role=alert] button").click()');
    await waitFor('!!document.querySelector(".asset-details dl")');
    await evaluate('document.querySelector(".asset-details button").click()');
    console.log("SMOKE details recovery PASS: stopped backend restarted, gallery preserved");
  }
  // D03-01: real Electron/preload/IPC/Python, no substitute renderer bridge.
  window.setSize(1180, 760);
  await evaluate(`document.querySelector('[aria-label="Duplicatas exatas"]').click()`);
  if (demo) {
    await waitFor('document.querySelectorAll(".group-select").length === 2');
    await evaluate('document.querySelector(".more-groups").click()');
    await waitFor('document.querySelectorAll(".group-select").length === 4');
    await evaluate('document.querySelectorAll(".group-select")[1].click()');
    await waitFor('document.querySelectorAll(".duplicate-members > li").length === 3');
    if (!await evaluate('document.querySelector(".duplicate-group").textContent.includes("Hardlink simulado")')) throw new Error("missing hardlink state");
    await evaluate('document.querySelectorAll(".group-select")[2].click()');
    await waitFor('document.querySelectorAll(".duplicate-members > li").length === 2');
    if (!await evaluate('document.querySelector(".duplicate-group").textContent.includes("histórica desatualizada")')) throw new Error("missing stale review");
    await evaluate('document.querySelectorAll(".group-select")[3].click()');
    await waitFor('document.querySelectorAll(".duplicate-members > li").length === 24');
    await writeFile("/tmp/playmemories-d03-01-duplicates.png", (await window.webContents.capturePage()).toPNG());
    for (const count of [48, 72, 96, 105]) {
      await evaluate('document.querySelector(".more-members").click()');
      await waitFor(`document.querySelectorAll(".duplicate-members > li").length === ${count}`);
    }
    const locations = await evaluate<string[]>('Array.from(document.querySelectorAll(".duplicate-members > li"), li => li.querySelectorAll("p")[4].textContent)');
    if (new Set(locations).size !== 105) throw new Error("lost or duplicated members");
    await evaluate('document.querySelector(".member-details").click()');
    await waitFor('!!document.querySelector(".asset-details dl")');
    await writeFile("/tmp/playmemories-d03-01-member-details.png", (await window.webContents.capturePage()).toPNG());
    window.webContents.sendInputEvent({type: "keyDown", keyCode: "Escape"});
    window.webContents.sendInputEvent({type: "keyUp", keyCode: "Escape"});
    await waitFor('!document.querySelector(".asset-details")');
    if (!await evaluate('document.activeElement.classList.contains("member-details")')) throw new Error("member focus not restored");
    for (const [width, height] of [[1180, 760], [860, 560], [760, 560], [760, 520]]) {
      window.setSize(width, height);
      await new Promise((resolve) => setTimeout(resolve, 100));
      if (await evaluate('document.documentElement.scrollWidth > innerWidth')) throw new Error(`duplicate overflow at ${width}x${height}`);
      await writeFile(`/tmp/playmemories-d03-01-${width}x${height}.png`, (await window.webContents.capturePage()).toPNG());
    }
    // Restart invalidates the projection and selection while preserving gallery cards.
    await evaluate('window.photoManager.retryGallery()');
    await waitFor('!document.querySelector(".duplicate-group") && document.querySelectorAll(".group-select").length === 2');
    await evaluate(`document.querySelector('[aria-label="Biblioteca"]').click()`);
    if (!await evaluate('document.querySelectorAll(".media-card").length === 73')) throw new Error("gallery lost through duplicate navigation");
    console.log("SMOKE D03-01 PASS: four groups, hardlinks, stale review, 105 unique members, D02C details/focus, resize, restart, 73 Assets preserved");
  } else {
    await waitFor('document.querySelector(".duplicates-view")?.textContent.includes("Nenhuma mídia foi analisada")');
    if (await evaluate('!!document.querySelector(".duplicates-view button")')) throw new Error("misleading capability retry");
    await writeFile("/tmp/playmemories-d03-01-normal.png", (await window.webContents.capturePage()).toPNG());
    await evaluate(`document.querySelector('[aria-label="Biblioteca"]').click()`);
    console.log("SMOKE D03-01 normal PASS: analysis_not_available, no retry or scan");
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

// Production preload/IPC/supervisor/Python; only the native selection source is
// supplied by the temporary harness in main. This does not validate native dialogs.
async function smokeLibraries(window: BrowserWindow, backend: PythonBackend, mediaRoot?: string): Promise<void> {
  const evaluate = <T>(code: string): Promise<T> => window.webContents.executeJavaScript(code);
  for (let attempt = 0; attempt < 100; attempt++) {
    if (await evaluate<boolean>('!!document.querySelector(".library-welcome")')) break;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  type State = {state: string; session: {session_id: string; library_handle: string; display_name: string} | null; error?: string};
  const state = () => evaluate<State>('window.photoManager.getLibraryState()');
  if ((await state()).state !== "no_library") throw new Error("smoke must start with no library");
  if ((await evaluate<State>('window.photoManager.chooseCreateLibrary()')).state !== "no_library") throw new Error("cancel created library");
  const first = await evaluate<State>('window.photoManager.chooseCreateLibrary()');
  if (first.session?.display_name !== "A.sqlite3") throw new Error("creation failed");
  await evaluate('window.photoManager.setReopenLibrary(true)');
  const second = await evaluate<State>('window.photoManager.chooseCreateLibrary()');
  if (second.session?.session_id === first.session?.session_id || second.session?.display_name !== "B.sqlite3") throw new Error("switch failed");
  await evaluate(`window.photoManager.closeLibrary(${JSON.stringify(second.session!.session_id)})`);
  if ((await state()).state !== "no_library") throw new Error("close failed");
  const reopened = await evaluate<State>('window.photoManager.chooseOpenLibrary()');
  if (reopened.session?.display_name !== "A.sqlite3") throw new Error("open failed");
  await backend.stop();
  await evaluate('window.photoManager.retryGallery()');
  const restarted = await state();
  if (restarted.session?.session_id === reopened.session?.session_id || restarted.session?.library_handle !== reopened.session?.library_handle) throw new Error("restart session failed");
  if (process.env.PLAYMEMORIES_DESKTOP_INGESTION_LAB === "1") await smokePreparation(window, restarted.session!.session_id, mediaRoot);
  await evaluate('window.photoManager.setReopenLibrary(false)');
  await evaluate(`window.photoManager.closeLibrary(${JSON.stringify(restarted.session!.session_id)})`);
  const missing = await evaluate<State>('window.photoManager.chooseOpenLibrary()');
  if (missing.error !== "not_found" || missing.state !== "no_library") throw new Error("missing catalog recreated");
  await evaluate('window.photoManager.forgetLibrary()');
  if (await evaluate<boolean>('typeof process !== "undefined" || typeof require !== "undefined" || "invoke" in window.photoManager')) throw new Error("renderer authority widened");
  console.log("SMOKE D04-01B PASS: synthetic selections, cancel/create/open/switch/close/restart, missing rejected; native dialogs NOT TESTED");
}


async function smokePreparation(window: BrowserWindow, session: string, mediaRoot?: string): Promise<void> {
  const evaluate = <T>(code: string): Promise<T> => window.webContents.executeJavaScript(code);
  const id = JSON.stringify(session);
  if (!await evaluate<boolean>(`window.photoManager.chooseMediaRoot(${id}).then(r => r.cancelled === true)`)) throw new Error("selection cancel registered root");
  const wait = async (operation: string, expected: string) => {
    for (let attempt = 0; attempt < 40; attempt++) {
      const status = await evaluate<{state: string; proposal_id: string | null}>(`window.photoManager.getPreparationStatus(${id}, ${JSON.stringify(operation)})`);
      if (status.state === expected) return status;
      if (["failed", "cancelled", "completed"].includes(status.state)) throw new Error("unexpected preparation terminal state");
      await new Promise((done) => setTimeout(done, 250));
    }
    throw new Error("preparation smoke timeout");
  };
  const grant = await evaluate<{root_grant_id: string}>(`window.photoManager.chooseMediaRoot(${id})`);
  const job = await evaluate<{operation_id: string}>(`window.photoManager.prepareCataloging(${id}, ${JSON.stringify(grant.root_grant_id)}, true)`);
  const complete = await wait(job.operation_id, "completed");
  const page = await evaluate<{items: unknown[]}>(`window.photoManager.listCatalogingCandidates(${id}, ${JSON.stringify(complete.proposal_id)}, null, 50)`);
  if (page.items.length !== 0) throw new Error("synthetic empty root is not empty");
  const another = await evaluate<{root_grant_id: string}>(`window.photoManager.chooseMediaRoot(${id})`);
  const cancelled = await evaluate<{operation_id: string}>(`window.photoManager.prepareCataloging(${id}, ${JSON.stringify(another.root_grant_id)}, true)`);
  await evaluate(`window.photoManager.cancelPreparation(${id}, ${JSON.stringify(cancelled.operation_id)})`);
  await wait(cancelled.operation_id, "cancelled");
  console.log("SMOKE D04-02A IPC PASS: synthetic cancel/select/prepare/status/page/cancel/reap; native dialogs NOT TESTED");
  if (!mediaRoot) throw new Error("missing synthetic application root");
  await smokeApplication(window, mediaRoot);

}

function syntheticJpeg(): Buffer {
  // Generated solely from an 80×40 solid-color fixture with EXIF leap-day capture.
  return Buffer.from("/9j/4AAQSkZJRgABAQAAAQABAAD/4QBIRXhpZgAATU0AKgAAAAgAAYdpAAQAAAABAAAAGgAAAAAAAZADAAIAAAAUAAAALAAAAAAyMDI0OjAyOjI5IDEyOjAwOjAwAP/bAEMACAYGBwYFCAcHBwkJCAoMFA0MCwsMGRITDxQdGh8eHRocHCAkLicgIiwjHBwoNyksMDE0NDQfJzk9ODI8LjM0Mv/bAEMBCQkJDAsMGA0NGDIhHCEyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMv/CABEIACgAUAMBIgACEQEDEQH/xAAVAAEBAAAAAAAAAAAAAAAAAAAABf/EABUBAQEAAAAAAAAAAAAAAAAAAAAF/9oADAMBAAIQAxAAAAGcLUwAAAAAAAAAAAAAD//EABQQAQAAAAAAAAAAAAAAAAAAAFD/2gAIAQEAAQUCS//EABQRAQAAAAAAAAAAAAAAAAAAADD/2gAIAQMBAT8Bf//EABQRAQAAAAAAAAAAAAAAAAAAADD/2gAIAQIBAT8Bf//EABQQAQAAAAAAAAAAAAAAAAAAAFD/2gAIAQEABj8CS//EABQQAQAAAAAAAAAAAAAAAAAAAFD/2gAIAQEAAT8hS//aAAwDAQACAAMAAAAQ888888888888888//8QAFBEBAAAAAAAAAAAAAAAAAAAAMP/aAAgBAwEBPxB//8QAFBEBAAAAAAAAAAAAAAAAAAAAMP/aAAgBAgEBPxB//8QAFBABAAAAAAAAAAAAAAAAAAAAUP/aAAgBAQABPxBL/9k=", "base64");
}
async function smokeApplication(window: BrowserWindow, root: string): Promise<void> {
  const evaluate = <T>(code: string): Promise<T> => window.webContents.executeJavaScript(code);
  const waitFor = async (expression: string) => {
    for (let i = 0; i < 150; i++) { if (await evaluate<boolean>(expression)) return; await new Promise((done) => setTimeout(done, 50)); }
    throw new Error(`application smoke timeout: ${expression}`);
  };
  const jpeg = syntheticJpeg();
  await writeFile(join(root, "synthetic-a.jpg"), jpeg);
  await writeFile(join(root, "synthetic-b.jpg"), jpeg);
  await writeFile(join(root, "excluded.txt"), "synthetic excluded file");
  const click = (text: string) => evaluate(`Array.from(document.querySelectorAll("button")).find(b => b.textContent === ${JSON.stringify(text)}).click()`);
  await click("+ Adicionar pastas");
  await click("Selecionar pasta");
  await waitFor('Array.from(document.querySelectorAll("button")).some(b => b.textContent === "Preparar proposta" && !b.disabled)');
  await click("Preparar proposta");
  await waitFor('Array.from(document.querySelectorAll("button")).some(b => b.textContent === "Ver proposta")');
  await click("Ver proposta");
  await waitFor('!!document.querySelector(".cataloging-review")');
  await click("Selecionar elegíveis desta página");
  await writeFile("/tmp/playmemories-d04-02b-review.png", (await window.webContents.capturePage()).toPNG());
  await click("Catalogar selecionados");
  await waitFor('document.querySelector(".cataloging-result")?.textContent.includes("2 item(ns) adicionado(s)")');
  await waitFor('document.querySelectorAll(".media-card").length === 2');
  await click("Ver itens na biblioteca");
  await evaluate('document.querySelector(".card-select").click()');
  await waitFor('!!document.querySelector(".asset-details dl")');
  await writeFile("/tmp/playmemories-d04-02b-catalog.png", (await window.webContents.capturePage()).toPNG());
  if (!Buffer.from(await readFile(join(root, "synthetic-a.jpg"))).equals(jpeg) || !Buffer.from(await readFile(join(root, "synthetic-b.jpg"))).equals(jpeg)) throw new Error("synthetic originals changed");
  await waitFor('document.querySelectorAll(".synthetic-thumbnail").length === 2 && [...document.querySelectorAll(".synthetic-thumbnail")].every(img => img.complete && img.naturalWidth === 256)');
  await evaluate('document.querySelector(".open-image").click()');
  await waitFor('document.querySelector(".image-viewer img")?.naturalWidth > 0');
  await writeFile("/tmp/playmemories-image-viewer.png", (await window.webContents.capturePage()).toPNG());
  await click("Fechar imagem");
  await click("Fechar detalhes");
  await click("Calendário");
  await waitFor('document.querySelector(".calendar-years button")?.textContent.includes("2024")');
  await evaluate('document.querySelector(".calendar-years button").click()');
  await waitFor('!!Array.from(document.querySelectorAll(".calendar-months button")).find(b=>b.textContent.includes("Fevereiro") && !b.disabled)');
  await evaluate('Array.from(document.querySelectorAll(".calendar-months button")).find(b=>b.textContent.includes("Fevereiro")).click()');
  await waitFor('document.querySelectorAll(".calendar-days button").length === 29');
  await writeFile("/tmp/playmemories-capture-calendar.png", (await window.webContents.capturePage()).toPNG());
  await evaluate(`document.querySelector('[aria-label="2024-02-29: 2 foto(s)"]').click()`);
  await waitFor('document.querySelectorAll(".media-card").length === 2 && document.querySelector(".gallery-filters").textContent.includes("2024-02-29")');
  await evaluate('document.querySelector(".favorite-toggle").click()');
  await waitFor('document.querySelector(".favorite-toggle").getAttribute("aria-pressed") === "true"');
  await click("☆ Favoritos");
  await waitFor('document.querySelectorAll(".media-card").length === 1');
  await evaluate('document.querySelector(".favorite-toggle").click()');
  await waitFor('document.querySelectorAll(".media-card").length === 0 && document.querySelector(".status-panel h2")?.textContent === "Nenhum favorito encontrado"');
  console.log("SMOKE FAVORITES PASS: explicit mark/global filtered list/unmark/empty; originals unchanged");
  console.log("SMOKE MEDIA CALENDAR PASS: progressive JPEG/real thumbnails/decoded preview/EXIF/capture year-month-leap-day/filter; originals unchanged");
  console.log("SMOKE D04-02B VISIBLE PASS: review/select/confirm-fixture/application-worker/commit/gallery-refresh/details; originals unchanged; native dialogs NOT TESTED");
}
