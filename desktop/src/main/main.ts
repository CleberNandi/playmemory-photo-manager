import { app, BrowserWindow, ipcMain } from "electron";
import { join, resolve } from "node:path";
import { PythonBackend } from "./backend.js";

const backend = new PythonBackend();
let quitting = false;

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
  ipcMain.handle("gallery:list", (_event, params: { pageSize?: number; after?: string | null }) =>
    backend.request("gallery.list", { page_size: params.pageSize, after: params.after }),
  );
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
