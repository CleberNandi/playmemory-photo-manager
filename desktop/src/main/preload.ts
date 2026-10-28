import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("photoManager", {
  listGallery: (params: { pageSize?: number; after?: string | null } = {}) =>
    ipcRenderer.invoke("gallery:list", params),
  retryGallery: () => ipcRenderer.invoke("backend:retry"),
});
