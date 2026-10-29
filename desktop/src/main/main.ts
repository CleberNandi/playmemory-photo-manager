import { app, BrowserWindow, ipcMain, session } from "electron";
import { join, resolve } from "node:path";
import { smoke } from "./smoke.js";
import { duplicatesRequest } from "./duplicates.js";
import { PythonBackend } from "./backend.js";

const backend = new PythonBackend();
let quitting = false;
let thumbnailRequests = 0;

backend.on("diagnostic", (message: string) => console.warn(message));
backend.on("failure", (error: Error) => console.warn(`backend failure: ${error.message}`));

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
  ipcMain.handle("gallery:list", (_event, params: { pageSize?: number; after?: string | null }) =>
    backend.request("gallery.list", { page_size: params.pageSize, after: params.after }),
  );
  ipcMain.handle("asset:details", async (_event, assetId: unknown) => {
    if (typeof assetId !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(assetId)) return {status: "invalid_request"};
    try { return {status: "ready", details: await backend.request("asset.details", {asset_id: assetId})}; }
    catch (error) {
      const code = (error as {code?: string}).code;
      return {status: code === "not_found" ? "not_found" : code === "backend_failure" ? "internal_error" : "temporarily_unavailable"};
    }
  });
  ipcMain.handle("thumbnail:get", async (_event, assetId: unknown) => {
    if (typeof assetId !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(assetId)) throw new Error("invalid asset identifier");
    if (thumbnailRequests >= 4) throw new Error("thumbnail busy");
    thumbnailRequests++;
    try { return await backend.request("thumbnail.get", {asset_id: assetId}); }
    finally { thumbnailRequests--; }
  });
  ipcMain.handle("duplicates:list", (_event, params: unknown) => duplicatesRequest(backend, "duplicates.list", params));
  ipcMain.handle("duplicates:group", (_event, params: unknown) => duplicatesRequest(backend, "duplicates.group", params));
  ipcMain.handle("backend:retry", async () => {
    await backend.restart();
    for (const target of BrowserWindow.getAllWindows()) target.webContents.send("backend:reset");
    return backend.request("gallery.list", { page_size: 24 });
  });
  try { await backend.start(); } catch { /* Renderer presents a recoverable backend error. */ }
  const window = createWindow();
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
  void backend.stop().finally(() => app.quit());
});
