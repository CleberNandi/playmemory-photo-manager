import { app, BrowserWindow, dialog, ipcMain, session } from "electron";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { LibraryController } from "./libraries.js";
import { LibraryPreferences, canonicalId } from "./library-preferences.js";
import { trustedSender } from "./trusted-ipc.js";
import { smoke } from "./smoke.js";
import { duplicatesRequest } from "./duplicates.js";
import { PythonBackend } from "./backend.js";

const backend = new PythonBackend();
let quitting = false;
let thumbnailRequests = 0;
let mainWindow: BrowserWindow | null = null;
let libraries: LibraryController;
let recovering = false;
const demo = process.env.PLAYMEMORIES_DESKTOP_DEMO === "1";
const smokeDirectory = process.env.PLAYMEMORIES_DESKTOP_SMOKE === "1" || process.env.PLAYMEMORIES_DESKTOP_LIBRARY_LAB === "1" ? mkdtempSync(join(tmpdir(), "pm-desktop-smoke-")) : null;
if (smokeDirectory) app.setPath("userData", smokeDirectory);
const smokeSelections = smokeDirectory && process.env.PLAYMEMORIES_DESKTOP_SMOKE === "1" && !demo ? [null, join(smokeDirectory, "A.sqlite3"), join(smokeDirectory, "B.sqlite3"), join(smokeDirectory, "A.sqlite3"), join(smokeDirectory, "missing.sqlite3")] : null;
const rendererFile = resolve(import.meta.dirname, "../renderer/index.html");
const expectedUrl = process.env.VITE_DEV_SERVER_URL ? new URL(process.env.VITE_DEV_SERVER_URL).href : pathToFileURL(rendererFile).href;

backend.on("diagnostic", (message: string) => console.warn(message));
backend.on("failure", () => {
  console.warn("backend unavailable");
  libraries?.invalidate();
  mainWindow?.webContents.send("backend:reset");
});

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 760,
    minHeight: 520,
    backgroundColor: "#f5f1e8",
    webPreferences: {
      preload: join(import.meta.dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) void window.loadURL(devUrl);
  else void window.loadFile(resolve(import.meta.dirname, "../renderer/index.html"));
  return window;
}

app.whenReady().then(async () => {
  session.defaultSession.setPermissionCheckHandler(() => false);
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
  const preference = new LibraryPreferences(app.getPath("userData"));
  libraries = new LibraryController(backend, preference, {choose: async (create) => {
    // Explicit automated smoke uses only harness-owned temporary selections;
    // native dialogs are validated separately in KDE, never claimed by this smoke.
    if (smokeSelections) return smokeSelections.shift() ?? null;
    if (!mainWindow) return null;
    if (create) {
      const selection = await dialog.showSaveDialog(mainWindow, {title: "Criar biblioteca fora das pastas de fotografias", defaultPath: join(app.getPath("userData"), "catalog.sqlite3"), filters: [{name: "Catálogo SQLite", extensions: ["sqlite3"]}], properties: ["showOverwriteConfirmation"]});
      if (selection.canceled || !selection.filePath) return null;
      const confirmation = await dialog.showMessageBox(mainWindow, {type: "question", title: "Criar biblioteca", message: "Criar um catálogo novo neste destino?", detail: "Escolha um local fora do acervo. Nenhuma fotografia será lida ou modificada. Arquivos existentes nunca são sobrescritos.", buttons: ["Cancelar", "Criar"], defaultId: 0, cancelId: 0});
      return confirmation.response === 1 ? selection.filePath : null;
    }
    const selection = await dialog.showOpenDialog(mainWindow, {title: "Abrir biblioteca existente", properties: ["openFile"], filters: [{name: "Catálogo SQLite", extensions: ["sqlite3", "sqlite", "db"]}]});
    return selection.canceled ? null : selection.filePaths[0] ?? null;
  }});
  const register = (channel: string, count: number, handler: (...args: unknown[]) => unknown) => {
    ipcMain.handle(channel, (event, ...args: unknown[]) => {
      if (!trustedSender(event, mainWindow, expectedUrl) || args.length !== count) throw new Error("invalid_request");
      if (recovering && channel !== "library:state") throw new Error("busy");
      return handler(...args);
    });
  };
  const envelope = (raw: unknown) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw) || Object.keys(raw).sort().join() !== "params,sessionId") throw new Error("invalid_request");
    return raw as {sessionId: unknown; params: unknown};
  };
  const query = async (method: "gallery.list" | "asset.details" | "thumbnail.get", id: unknown, params: Record<string, unknown>) => {
    if (recovering || libraries.isBusy) throw new Error("busy");
    return demo ? backend.request(method, params) : libraries.query(method, id, params);
  };
  const demoState = () => ({state: "demo", session: null, reopen: false});
  register("library:state", 0, () => demo ? demoState() : libraries.current());
  register("library:create", 0, () => demo ? demoState() : libraries.choose(true));
  register("library:open", 0, () => demo ? demoState() : libraries.choose(false));
  register("library:close", 1, (id) => demo ? demoState() : libraries.close(id));
  register("library:reopen", 1, (value) => demo ? demoState() : libraries.setReopen(value));
  register("library:forget", 0, () => demo ? demoState() : libraries.forget());
  register("gallery:list", 1, (raw) => {
    const {sessionId, params} = envelope(raw);
    if (!params || typeof params !== "object" || Array.isArray(params)) throw new Error("invalid_request");
    const p = params as {pageSize?: unknown; after?: unknown};
    if (Object.keys(p).some((key) => !["pageSize", "after"].includes(key)) || (p.pageSize !== undefined && (!Number.isInteger(p.pageSize) || Number(p.pageSize) < 1 || Number(p.pageSize) > 50)) || (p.after !== undefined && p.after !== null && (typeof p.after !== "string" || p.after.length > 2048))) throw new Error("invalid_request");
    return query("gallery.list", sessionId, {page_size: p.pageSize ?? 24, after: p.after ?? null});
  });
  register("asset:details", 1, async (raw) => {
    const {sessionId, params: assetId} = envelope(raw);
    if (!canonicalId(assetId)) return {status: "invalid_request"};
    try { return {status: "ready", details: await query("asset.details", sessionId, {asset_id: assetId})}; }
    catch (error) {
      const code = (error as {code?: string}).code;
      return {status: code === "not_found" ? "not_found" : code === "backend_failure" ? "internal_error" : "temporarily_unavailable"};
    }
  });
  register("thumbnail:get", 1, async (raw) => {
    const {sessionId, params: assetId} = envelope(raw);
    if (!canonicalId(assetId)) throw new Error("invalid_request");
    if (thumbnailRequests >= 4) throw new Error("busy");
    thumbnailRequests++;
    try { return await query("thumbnail.get", sessionId, {asset_id: assetId}); }
    finally { thumbnailRequests--; }
  });
  for (const [channel, method] of [["duplicates:list", "duplicates.list"], ["duplicates:group", "duplicates.group"]] as const) {
    register(channel, 1, (raw) => {
      const {sessionId, params} = envelope(raw);
      const scoped = {request: (m: Parameters<PythonBackend["request"]>[0], p: Record<string, unknown> = {}) => {
        if (m !== "duplicates.list" && m !== "duplicates.group") throw new Error("invalid_request");
        return demo ? backend.request(m, p) : libraries.query(m, sessionId, p);
      }};
      return duplicatesRequest(scoped, method, params);
    });
  }
  register("backend:retry", 0, async () => {
    if (recovering || libraries.isBusy) throw new Error("busy");
    if (!demo && libraries.current().state === "active") {
      try { return await libraries.query("gallery.list", libraries.current().session?.session_id, {page_size: 24}); }
      catch (error) { if ((error as {code?: string}).code) throw error; }
    }
    if (libraries.isBusy) throw new Error("busy");
    recovering = true;
    libraries.invalidate();
    try {
      await backend.restart();
      if (!demo) await libraries.initialize();
      mainWindow?.webContents.send("backend:reset");
      return demo ? backend.request("gallery.list", {page_size: 24}) : libraries.query("gallery.list", libraries.current().session?.session_id, {page_size: 24});
    } finally { recovering = false; }
  });
  try { await backend.start(); if (!demo) await libraries.initialize(); }
  catch { libraries.invalidate(); }
  const window = createWindow();
  mainWindow = window;
  if (process.env.PLAYMEMORIES_DESKTOP_SMOKE === "1") {
    const watchdog = setTimeout(() => {
      console.error("SMOKE FAIL: timeout");
      process.exitCode = 1;
      app.quit();
    }, 45_000);
    window.webContents.once("render-process-gone", () => { process.exitCode = 1; app.quit(); });
    window.webContents.once("did-finish-load", () => {
      void smoke(window, backend).then(() => { clearTimeout(watchdog); app.quit(); }).catch((error: unknown) => {
        clearTimeout(watchdog);
        console.error(error);
        process.exitCode = 1;
        app.quit();
      });
    });
  }
  console.log("PlayMemories desktop ready (local backend supervised)");
  const smokeExit = Number.parseInt(process.env.PLAYMEMORIES_DESKTOP_SMOKE_EXIT_MS ?? "", 10);
  if (Number.isFinite(smokeExit) && smokeExit > 0) setTimeout(() => app.quit(), smokeExit);
});

app.on("window-all-closed", () => app.quit());
app.on("before-quit", (event) => {
  if (quitting) return;
  event.preventDefault();
  quitting = true;
  void backend.stop().finally(() => { if (smokeDirectory) rmSync(smokeDirectory, {recursive: true, force: true}); app.quit(); });
});
