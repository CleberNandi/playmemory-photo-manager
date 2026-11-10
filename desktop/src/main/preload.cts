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
  getIndexStatus:()=>ipcRenderer.invoke("index:status"),
  refreshFolders:()=>ipcRenderer.invoke("index:refresh"),
  onGalleryChanged:(listener:()=>void)=>{const notify=()=>listener();ipcRenderer.on("gallery:changed",notify);return ()=>ipcRenderer.removeListener("gallery:changed",notify);},
  listGallery: (params: { pageSize?: number; after?: string | null; capturePeriod?: string | null; favoritesOnly?: boolean } = {}) =>
    scoped("gallery:list", params),
  saveRotation:(assetId:string,angle:number,mode:"replace"|"copy")=>scoped("image:save",{assetId,angle,mode}),
  getImageSaveStatus:(jobId:string)=>scoped("image:save-status",jobId),
  showMediaMenu: (assetId:string)=>scoped("asset:menu",assetId),
  locateMedia: (assetId:string,describe=false)=>scoped("asset:locate",{assetId,describe}),
  getAssetDetails: (assetId: string) => scoped("asset:details", assetId),
  setFavorite: (assetId: string, favorite: boolean) => scoped("annotation:favorite", {assetId, favorite}),
  getCalendar: (period: string | null) => scoped("calendar:summary", period),
  getPreview: (assetId: string) => scoped("preview:get", assetId),
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
  openManagedLibrary: () => stateRequest("library:default"),
  addMediaFolder: (id: string) => ipcRenderer.invoke("folder:add",id),
  getFolderImportStatus: (id: string,job: string) => ipcRenderer.invoke("folder:status",id,job),
  stopFolderImport: (id: string,job: string) => ipcRenderer.invoke("folder:stop",id,job),
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
