import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("photoManager", {
  listGallery: (params: { pageSize?: number; after?: string | null } = {}) =>
    ipcRenderer.invoke("gallery:list", params),
  getAssetDetails: (assetId: string) => ipcRenderer.invoke("asset:details", assetId),
  getThumbnail: (assetId: string) => ipcRenderer.invoke("thumbnail:get", assetId),
  listDuplicates: (params: {pageSize?: number; after?: string | null} = {}) => ipcRenderer.invoke("duplicates:list", params),
  getDuplicateGroup: (params: {snapshotId: string; groupKey: string; pageSize?: number; after?: string | null}) => ipcRenderer.invoke("duplicates:group", params),
  onBackendReset: (listener: () => void) => {
    const notify = () => listener();
    ipcRenderer.on("backend:reset", notify);
    return () => ipcRenderer.removeListener("backend:reset", notify);
  },
  retryGallery: () => ipcRenderer.invoke("backend:retry"),
});
