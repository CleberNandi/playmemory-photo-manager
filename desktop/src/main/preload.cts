import { contextBridge, ipcRenderer } from "electron";

let sessionId: string | null = null;
let sequence = 0;
let applied = 0;
const stateRequest = async (channel: string, ...args: unknown[]) => {
  const request = ++sequence;
  const result = await ipcRenderer.invoke(channel, ...args);
  if (request >= applied) { applied = request; sessionId = result.session?.session_id ?? null; }
  return result;
};
const scoped = (channel: string, params: unknown) => ipcRenderer.invoke(channel, {sessionId, params});
ipcRenderer.on("backend:reset", () => { sessionId = null; applied = ++sequence; });

contextBridge.exposeInMainWorld("photoManager", {
  listGallery: (params: { pageSize?: number; after?: string | null } = {}) =>
    scoped("gallery:list", params),
  getAssetDetails: (assetId: string) => scoped("asset:details", assetId),
  getThumbnail: (assetId: string) => scoped("thumbnail:get", assetId),
  listDuplicates: (params: {pageSize?: number; after?: string | null} = {}) => scoped("duplicates:list", params),
  getDuplicateGroup: (params: {snapshotId: string; groupKey: string; pageSize?: number; after?: string | null}) => scoped("duplicates:group", params),
  chooseMediaRoot: (id: string) => ipcRenderer.invoke("ingestion:select", id),
  prepareCataloging: (id: string, grant: string, recursive: boolean) => ipcRenderer.invoke("ingestion:prepare", id, grant, recursive),
  getPreparationStatus: (id: string, operation: string) => ipcRenderer.invoke("ingestion:status", id, operation),
  cancelPreparation: (id: string, operation: string) => ipcRenderer.invoke("ingestion:cancel", id, operation),
  listCatalogingCandidates: (id: string, proposal: string, cursor: string | null, pageSize: number) => ipcRenderer.invoke("ingestion:page", id, proposal, cursor, pageSize),
  applyCataloging: (id: string, proposal: string, selection: string[]) => ipcRenderer.invoke("ingestion:apply", id, proposal, selection),
  getCatalogingApplicationStatus: (id: string, command: string) => ipcRenderer.invoke("ingestion:application-status", id, command),
  getLibraryState: () => stateRequest("library:state"),
  chooseCreateLibrary: () => stateRequest("library:create"),
  chooseOpenLibrary: () => stateRequest("library:open"),
  closeLibrary: (id: string) => stateRequest("library:close", id),
  setReopenLibrary: (value: boolean) => stateRequest("library:reopen", value),
  forgetLibrary: () => stateRequest("library:forget"),
  onBackendReset: (listener: () => void) => {
    const notify = () => listener();
    ipcRenderer.on("backend:reset", notify);
    return () => ipcRenderer.removeListener("backend:reset", notify);
  },
  retryGallery: () => ipcRenderer.invoke("backend:retry"),
});
