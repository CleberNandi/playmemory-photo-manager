import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("photoManager", {
  listGallery: (params: { pageSize?: number; after?: string | null } = {}) =>
    ipcRenderer.invoke("gallery:list", params),
  getThumbnail: (assetId: string) => ipcRenderer.invoke("thumbnail:get", assetId),
  retryGallery: () => ipcRenderer.invoke("backend:retry"),
});
