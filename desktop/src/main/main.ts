import { app, BrowserWindow, ipcMain, session } from "electron";
import { join, resolve } from "node:path";
import { PythonBackend } from "./backend.js";

const backend = new PythonBackend();
let quitting = false;

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
      preload: join(import.meta.dirname, "preload.js"),
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
  ipcMain.handle("backend:retry", async () => {
    await backend.restart();
    return backend.request("gallery.list", { page_size: 24 });
  });
  try { await backend.start(); } catch { /* Renderer presents a recoverable backend error. */ }
  createWindow();
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
