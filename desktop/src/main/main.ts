import { IndexCoordinator } from "./index-coordinator.js";
import { ImageEdits } from "./image-edits.js";
import { MediaActions, type MediaAction } from "./media-actions.js";
import { FolderImportController } from "./folder-import.js";
import { nativePath } from "./native-path.js";
import { randomUUID } from "node:crypto";
import { CatalogingController } from "./cataloging.js";
import { app, BrowserWindow, dialog, ipcMain, session, Menu, shell } from "electron";
import { basename, dirname, extname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { LibraryController } from "./libraries.js";
import { LibraryPreferences, canonicalId, ensurePrivateDirectory } from "./library-preferences.js";
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
let folderImports: FolderImportController;
let imageEdits: ImageEdits;
let indexer:IndexCoordinator|undefined;
const ingestionLab = process.env.PLAYMEMORIES_DESKTOP_INGESTION_LAB === "1";
const demo = process.env.PLAYMEMORIES_DESKTOP_DEMO === "1";
const managedSmoke=process.env.PLAYMEMORIES_DESKTOP_MANAGED_SMOKE === "1";
const managedMode=!demo && (process.env.PLAYMEMORIES_DESKTOP_SMOKE !== "1" || managedSmoke);
const smokeDirectory = process.env.PLAYMEMORIES_DESKTOP_SMOKE === "1" || demo ? mkdtempSync(join(tmpdir(), "pm-desktop-smoke-")) : null;
if (smokeDirectory) { app.setPath("userData", smokeDirectory); app.setPath("sessionData", smokeDirectory); }
const smokeSelections = smokeDirectory && process.env.PLAYMEMORIES_DESKTOP_SMOKE === "1" && !demo ? [null, join(smokeDirectory, "A.sqlite3"), join(smokeDirectory, "B.sqlite3"), join(smokeDirectory, "A.sqlite3"), join(smokeDirectory, "missing.sqlite3")] : null;
const ingestionSmokeDirectory = (ingestionLab||managedSmoke) && smokeSelections && smokeDirectory
  ? mkdtempSync(join(tmpdir(), "pm-ingestion-smoke-")) : null;
const ingestionSmokeRoot = ingestionSmokeDirectory && managedSmoke
  ? join(ingestionSmokeDirectory, "Acervo de teste") : ingestionSmokeDirectory;
if (ingestionSmokeRoot && ingestionSmokeRoot !== ingestionSmokeDirectory) mkdirSync(ingestionSmokeRoot);
const ingestionSelections = ingestionSmokeRoot ? [null, ingestionSmokeRoot, ingestionSmokeRoot, ingestionSmokeRoot, ingestionSmokeRoot] : null;
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
    backgroundColor: "#f5f5f5",
    webPreferences: {
      preload: join(import.meta.dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  if (process.platform !== "darwin") window.removeMenu();
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
      const physical = await nativePath(selection.filePath, true);
      const confirmation = await dialog.showMessageBox(mainWindow, {type: "question", title: "Criar biblioteca", message: "Criar um catálogo novo neste destino?", detail: `Seleção: ${selection.filePath}\nDestino físico: ${physical}\nEscolha um local fora do acervo. Nenhuma fotografia será lida ou modificada. Arquivos existentes nunca são sobrescritos.`, buttons: ["Cancelar", "Criar"], defaultId: 0, cancelId: 0});
      return confirmation.response === 1 ? physical : null;
    }
    const selection = await dialog.showOpenDialog(mainWindow, {title: "Abrir biblioteca existente", properties: ["openFile"], filters: [{name: "Catálogo SQLite", extensions: ["sqlite3", "sqlite", "db"]}]});
    if (selection.canceled || selection.filePaths.length !== 1) return null;
    return nativePath(selection.filePaths[0]);
  }}, managedMode ? async()=>{
    const folder=join(app.getPath("userData"),"library-state");
    await ensurePrivateDirectory(folder,true);
    return join(folder,"principal.sqlite3");
  } : undefined);
  const register = (channel: string, count: number, handler: (...args: unknown[]) => unknown) => {
    ipcMain.handle(channel, (event, ...args: unknown[]) => {
      if (!trustedSender(event, mainWindow, expectedUrl) || args.length !== count) throw new Error("invalid_request");
      if (recovering && channel !== "library:state") throw new Error("busy");
      const foregroundChannels=new Set(["library:create","library:open","library:close","library:default","annotation:favorite","annotation:edit","album:action","duplicates:start","image:save","folder:add","ingestion:select","ingestion:prepare","ingestion:apply"]);
      const result = indexer&&foregroundChannels.has(channel)?indexer.foreground(()=>handler(...args)):handler(...args);
      return channel.startsWith("library:") ? Promise.resolve(result).then((state) => ({...(state as object), cataloging_enabled: (ingestionLab||managedMode) && !demo, folder_import_enabled:managedMode})) : result;
    });
  };
  const envelope = (raw: unknown) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw) || Object.keys(raw).sort().join() !== "params,sessionId") throw new Error("invalid_request");
    return raw as {sessionId: unknown; params: unknown};
  };
  const query = async (method: "gallery.list" | "gallery.facets" | "calendar.summary" | "preview.get" | "asset.details" | "thumbnail.get", id: unknown, params: Record<string, unknown>) => {
    if (recovering || libraries.isBusy) throw new Error("busy");
    return demo ? backend.request(method, params) : libraries.query(method, id, params);
  };
  const demoState = () => ({state: "demo", session: null, reopen: false});
  register("index:status",0,()=>indexer?.current()??{state:"disabled",busy:false,revision:0,added_count:0,error:null,last_check:null});
  register("index:refresh",0,()=>indexer?.refresh());
  register("library:state", 0, () => demo ? demoState() : libraries.current());
  register("library:create", 0, () => demo ? demoState() : (folderImports?.busy||imageEdits?.busy)?{...libraries.current(),error:"busy"}:libraries.choose(true));
  register("library:open", 0, () => demo ? demoState() : (folderImports?.busy||imageEdits?.busy)?{...libraries.current(),error:"busy"}:libraries.choose(false));
  register("library:close", 1, (id) => demo ? demoState() : (folderImports?.busy||imageEdits?.busy)?{...libraries.current(),error:"busy"}:libraries.close(id));
  register("library:default",0,()=>demo?demoState():(folderImports?.busy||imageEdits?.busy)?{...libraries.current(),error:"busy"}:libraries.openManaged());
  register("library:reopen", 1, (value) => demo ? demoState() : libraries.setReopen(value));
  register("library:forget", 0, () => demo ? demoState() : libraries.forget());
  register("gallery:facets", 1, (raw) => {
    const {sessionId, params} = envelope(raw);
    if (!params || typeof params !== "object" || Array.isArray(params)) throw new Error("invalid_request");
    const {facet, keyword, offset} = params as Record<string, unknown>;
    if (Object.keys(params).length !== 3 || typeof facet !== "string" ||
        !["tags", "types", "cameras", "lenses"].includes(facet) ||
        typeof keyword !== "string" || keyword.length > 200 || keyword.includes("\0") ||
        typeof offset !== "number" || !Number.isSafeInteger(offset) || offset < 0 ||
        offset > Number.MAX_SAFE_INTEGER - 24) throw new Error("invalid_request");
    return query("gallery.facets", sessionId, {facet, keyword, offset});
  });
  register("album:action", 1, (raw) => {
    const {sessionId, params} = envelope(raw);
    if (demo || !params || typeof params !== "object" || Array.isArray(params)) throw new Error("invalid_request");
    const input = params as Record<string, unknown>;
    const keys = Object.keys(input).sort().join();
    if (input.action === "list" && keys === "action,offset" &&
        typeof input.offset === "number" && Number.isSafeInteger(input.offset) &&
        input.offset >= 0 && input.offset <= Number.MAX_SAFE_INTEGER - 50)
      return libraries.query("album.action", sessionId, input);
    if (input.action === "create" && keys === "action,name" && typeof input.name === "string" &&
        input.name.trim() && input.name.length <= 120 && !input.name.includes("\0"))
      return libraries.query("album.action", sessionId, input);
    if (input.action === "rename" && keys === "action,album_id,name" && canonicalId(input.album_id)
      && typeof input.name === "string" && input.name.trim().length > 0 && input.name.length <= 120 && !input.name.includes("\0"))
      return libraries.query("album.action", sessionId, input);
    if (input.action === "delete" && keys === "action,album_id" && canonicalId(input.album_id))
      return libraries.query("album.action", sessionId, input);
    if ((input.action === "add" || input.action === "remove") && keys === "action,album_id,asset_id" &&
        canonicalId(input.album_id) && canonicalId(input.asset_id))
      return libraries.query("album.action", sessionId, input);
    throw new Error("invalid_request");
  });
  register("gallery:list", 1, (raw) => {
    const {sessionId, params} = envelope(raw);
    if (!params || typeof params !== "object" || Array.isArray(params)) throw new Error("invalid_request");
    const p = params as {pageSize?: unknown; after?: unknown; capturePeriod?: unknown; favoritesOnly?: unknown; rootId?: unknown; folderPath?: unknown; albumId?: unknown; filters?: unknown};
    if (Object.keys(p).some((key) => !["pageSize", "after", "capturePeriod", "favoritesOnly", "rootId", "folderPath", "albumId", "filters"].includes(key)) || (p.pageSize !== undefined && (!Number.isInteger(p.pageSize) || Number(p.pageSize) < 1 || Number(p.pageSize) > 50)) || (p.after !== undefined && p.after !== null && (typeof p.after !== "string" || p.after.length > 2048))) throw new Error("invalid_request");
    if (p.capturePeriod !== undefined && p.capturePeriod !== null && (typeof p.capturePeriod !== "string" || !/^(undated|[0-9]{4}(-[0-9]{2}){0,2})$/.test(p.capturePeriod))) throw new Error("invalid_request");
    if (p.favoritesOnly !== undefined && typeof p.favoritesOnly !== "boolean") throw new Error("invalid_request");
    if (p.rootId !== undefined && (typeof p.rootId !== "string" || !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(p.rootId))) throw new Error("invalid_request");
    if (p.folderPath !== undefined && (p.rootId === undefined || typeof p.folderPath !== "string"
      || p.folderPath.length > 4096 || p.folderPath.includes("\0")
      || (p.folderPath !== "" && p.folderPath.split("/").some(part => ["", ".", ".."].includes(part))))) throw new Error("invalid_request");
    if (p.albumId !== undefined && !canonicalId(p.albumId)) throw new Error("invalid_request");
    const filters: Record<string, unknown> = {};
    if (p.filters !== undefined) {
      if (!p.filters || typeof p.filters !== "object" || Array.isArray(p.filters)) throw new Error("invalid_request");
      for (const [key, value] of Object.entries(p.filters)) {
        if (key === "rating") {
          if (typeof value !== "number" || !Number.isInteger(value) || value < 1 || value > 5) throw new Error("invalid_request");
        } else if (key === "tag_id") {
          if (!canonicalId(value)) throw new Error("invalid_request");
        } else if (!["keyword", "media_type", "camera", "lens"].includes(key)
          || typeof value !== "string" || value.length > 200 || value.includes("\0")) throw new Error("invalid_request");
        filters[key] = value;
      }
    }
    return query("gallery.list", sessionId, {...filters, ...(p.albumId ? {album_id:p.albumId} : {}), include_facets:!p.after, include_roots:!p.after, ...(p.folderPath !== undefined ? {folder_path:p.folderPath} : {}), ...(p.rootId ? {root_id:p.rootId} : {}), page_size: p.pageSize ?? 24, after: p.after ?? null, ...(p.capturePeriod ? {capture_period:p.capturePeriod} : {}), ...(p.favoritesOnly !== undefined ? {favorites_only:p.favoritesOnly} : {})});
  });
  imageEdits=new ImageEdits(libraries,async(source,angle)=>{
    if(managedSmoke&&smokeDirectory&&ingestionSmokeRoot&&dirname(source)===ingestionSmokeRoot)return join(dirname(source),basename(source,extname(source))+"-rotacionada"+extname(source));
    if(!mainWindow)return null;
    const extension=extname(source);
    const result=await dialog.showSaveDialog(mainWindow,{title:`Salvar cópia rotacionada ${angle}° na mesma pasta`,defaultPath:join(dirname(source),basename(source,extension)+"-rotacionada"+extension),message:"Escolha um nome novo na mesma pasta do original. Arquivos existentes não serão substituídos.",filters:[{name:"Imagem no formato original",extensions:[extension.slice(1)]}]});
    return result.canceled||!result.filePath?null:nativePath(result.filePath,true);
  },async(source,angle)=>{
    if(managedSmoke&&smokeDirectory&&ingestionSmokeRoot&&dirname(source)===ingestionSmokeRoot)return true;
    if(!mainWindow)return false;
    const result=await dialog.showMessageBox(mainWindow,{type:"warning",title:"Salvar alterações no arquivo original",message:`Substituir a imagem original pela versão rotacionada ${angle}°?`,detail:source+"\nA imagem será gravada em resolução original. JPEG será recomprimido; metadados podem ser normalizados. Salvar como cópia preserva o original.",buttons:["Cancelar","Salvar alterações"],defaultId:0,cancelId:0});
    return result.response===1;
  });
  register("image:save",1,(raw)=>{
    const {sessionId,params}=envelope(raw);
    if(demo||folderImports?.busy||!params||typeof params!=="object"||Array.isArray(params)||Object.keys(params).sort().join()!=="angle,assetId,mode")throw new Error("invalid_request");
    const p=params as {assetId:unknown;angle:unknown;mode:unknown};return imageEdits.start(sessionId,p.assetId,p.angle,p.mode);
  });
  register("image:save-status",1,(raw)=>{const {sessionId,params}=envelope(raw);return imageEdits.status(sessionId,params);});
  const mediaActions=new MediaActions(libraries,async(items)=>{
    if(!mainWindow||mainWindow.isDestroyed())return null;
    const window=mainWindow;
    return new Promise<MediaAction|null>(resolve=>{
      let selected:MediaAction|null=null;
      const menu=Menu.buildFromTemplate(items.map(item=>({label:item.label,enabled:item.enabled,click:()=>{selected=item.action;}})));
      menu.popup({window,callback:()=>resolve(selected)});
    });
  },path=>shell.showItemInFolder(path),async(path)=>{
    if(!mainWindow||mainWindow.isDestroyed())return false;
    const result=await dialog.showMessageBox(mainWindow,{type:"info",title:"Localização do arquivo",message:"Arquivo original",detail:path,buttons:["Fechar","Abrir pasta"],defaultId:0,cancelId:0});
    return result.response===1;
  });
  register("asset:menu",1,async(raw)=>{
    const {sessionId,params}=envelope(raw);
    if(demo||!canonicalId(params))return null;
    try{return await mediaActions.menu(sessionId,params);}catch{throw new Error("unavailable");}
  });
  register("asset:locate",1,async(raw)=>{
    const {sessionId,params}=envelope(raw);
    if(demo||!params||typeof params!=="object"||Array.isArray(params)||Object.keys(params).sort().join()!=="assetId,describe")throw new Error("invalid_request");
    const p=params as {assetId:unknown;describe:unknown};
    if(!canonicalId(p.assetId)||typeof p.describe!=="boolean")throw new Error("invalid_request");
    try{return await mediaActions.locate(sessionId,p.assetId,p.describe);}catch{return {status:"unavailable"};}
  });
  register("annotation:edit", 1, (raw) => {
    if (demo || folderImports.busy || imageEdits.busy) throw new Error("unavailable");
    const {sessionId, params} = envelope(raw);
    if (!params || typeof params !== "object" || Array.isArray(params)
      || Object.keys(params).sort().join() !== "assetId,field,value") throw new Error("invalid_request");
    const {assetId, field, value} = params as Record<string, unknown>;
    if (!canonicalId(assetId)) throw new Error("invalid_request");
    switch (field) {
      case "rating":
        if (value !== null && (typeof value !== "number" || !Number.isInteger(value) || value < 1 || value > 5)) throw new Error("invalid_request");
        break;
      case "tag_remove":
        if (!canonicalId(value)) throw new Error("invalid_request");
        break;
      case "title":
      case "description":
      case "tag_add": {
        if (value === null && field !== "tag_add") break;
        const limit = field === "description" ? 2000 : field === "title" ? 200 : 100;
        if (typeof value !== "string" || value.length > limit || value.includes("\0")) throw new Error("invalid_request");
        break;
      }
      default: throw new Error("invalid_request");
    }
    return libraries.query("annotation.edit", sessionId, {asset_id:assetId, field, value});
  });
  register("annotation:favorite", 1, (raw) => {
    const {sessionId, params} = envelope(raw);
    if (demo) throw new Error("unavailable");
    if (!params || typeof params !== "object" || Array.isArray(params) || Object.keys(params).sort().join() !== "assetId,favorite") throw new Error("invalid_request");
    const p = params as {assetId: unknown; favorite: unknown};
    if (!canonicalId(p.assetId) || typeof p.favorite !== "boolean") throw new Error("invalid_request");
    return libraries.setFavorite(sessionId, p.assetId as string, p.favorite);
  });
  register("calendar:summary", 1, (raw) => {
    const {sessionId, params: period} = envelope(raw);
    if (period !== null && (typeof period !== "string" || !/^[0-9]{4}(-[0-9]{2})?$/.test(period))) throw new Error("invalid_request");
    return query("calendar.summary", sessionId, {period});
  });
  register("preview:get", 1, async (raw) => {
    const {sessionId, params} = envelope(raw);
    let request: Record<string, unknown>;
    if (canonicalId(params)) {
      request = {asset_id: params};
    } else {
      if (!params || typeof params !== "object" || Array.isArray(params)) throw new Error("invalid_request");
      const {assetId, variant, offset} = params as Record<string, unknown>;
      if (Object.keys(params).some(key => !["assetId", "variant", "offset"].includes(key))
        || !canonicalId(assetId) || (variant !== "dimensions" && variant !== "original")
        || (offset !== undefined && (variant !== "original" || typeof offset !== "number"
          || !Number.isInteger(offset) || offset < 0 || offset >= 16 * 1024 * 1024))) throw new Error("invalid_request");
      if (demo) return null;
      request = {asset_id:assetId, variant, ...(offset === undefined ? {} : {offset})};
    }
    if (thumbnailRequests >= 4) return {status:"pending"};
    thumbnailRequests++;
    try { return await query("preview.get", sessionId, request); }
    finally { thumbnailRequests--; }
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
    if (thumbnailRequests >= 4) return {status:"pending"};
    thumbnailRequests++;
    try { return await query("thumbnail.get", sessionId, {asset_id: assetId}); }
    finally { thumbnailRequests--; }
  });
  register("rename:preview", 1, (raw) => {
    const {sessionId, params} = envelope(raw);
    if (demo || !params || typeof params !== "object" || Array.isArray(params)) throw new Error("invalid_request");
    const input = params as Record<string, unknown>;
    if (Object.keys(input).sort().join() !== "assetId,locationId,stem" ||
        !canonicalId(input.assetId) || !canonicalId(input.locationId) ||
        typeof input.stem !== "string" || [...input.stem].length > 255) throw new Error("invalid_request");
    return libraries.query("rename.preview", sessionId, {
      asset_id: input.assetId, location_id: input.locationId, stem: input.stem,
    });
  });
  register("devices:list", 1, (raw) => {
    const {sessionId, params} = envelope(raw);
    if (demo || params !== null) throw new Error("invalid_request");
    return libraries.query("devices.list", sessionId, {});
  });
  for (const [channel, method] of [["duplicates:start", "duplicates.start"], ["duplicates:list", "duplicates.list"], ["duplicates:group", "duplicates.group"]] as const) {
    register(channel, 1, (raw) => {
      const {sessionId, params} = envelope(raw);
      const scoped = {request: (m: Parameters<PythonBackend["request"]>[0], p: Record<string, unknown> = {}) => {
        if (m !== "duplicates.start" && m !== "duplicates.list" && m !== "duplicates.group") throw new Error("invalid_request");
        if (demo && m === "duplicates.start") return Promise.resolve({status: "invalid_request"});
        return demo ? backend.request(m, p) : libraries.query(m, sessionId, p);
      }};
      return duplicatesRequest(scoped, method, params);
    });
  }
  const windowId=randomUUID();
  const cataloging = new CatalogingController(backend, libraries, windowId, (ingestionLab||managedMode) && !demo, async () => {
    if (ingestionSelections) return ingestionSelections.shift() ?? null;
    if (!mainWindow) return null;
    const selected = await dialog.showOpenDialog(mainWindow, {title: "Selecionar pasta de fotografias", properties: ["openDirectory"]});
    if (selected.canceled || selected.filePaths.length !== 1) return null;
    const physical = await nativePath(selected.filePaths[0]);
    const answer = await dialog.showMessageBox(mainWindow, {type: "question", title: "Preparar catalogação", message: "Autorizar leitura recursiva desta pasta?", detail: `Seleção: ${selected.filePaths[0]}\nDestino físico: ${physical}\nA configuração da raiz será registrada no catálogo. Arquivos e metadados serão examinados, sem modificar originais ou catalogar fotos nesta etapa. Ao reutilizar uma raiz, sua identidade histórica pode não estar disponível: confirme o destino atual.`, buttons: ["Cancelar", "Preparar"], defaultId: 0, cancelId: 0});
    return answer.response === 1 ? physical : null;
  }, async (count) => {
    if (!mainWindow) return false;
    if (process.env.PLAYMEMORIES_DESKTOP_SMOKE === "1") return true;
    const state = libraries.current();
    const answer = await dialog.showMessageBox(mainWindow, {
      type: "question", title: "Confirmar catalogação",
      message: `Adicionar ${count} item(ns) escolhido(s) à biblioteca?`,
      detail: `Biblioteca: ${state.session?.display_name ?? ""}\nSomente os candidatos selecionados serão registrados no catálogo. Os arquivos originais não serão movidos nem modificados. Se algum item tiver mudado, o lote inteiro será bloqueado.`,
      buttons: ["Cancelar", "Catalogar selecionados"], defaultId: 0, cancelId: 0,
    });
    return answer.response === 1;
  });
  const folderSelections=managedSmoke&&ingestionSmokeRoot?[null,ingestionSmokeRoot,ingestionSmokeRoot,join(ingestionSmokeRoot,"teste")]:null;
  folderImports=new FolderImportController(backend,libraries,windowId,async()=>{
    if(folderSelections)return folderSelections.shift()??null;
    if(!mainWindow)return null;
    const result=await dialog.showOpenDialog(mainWindow,{title:"Adicionar pasta e subpastas à biblioteca",message:"A pasta será acompanhada para carregar imagens novas automaticamente. Os originais permanecem inalterados.",properties:["openDirectory"]});
    return result.canceled||result.filePaths.length!==1?null:nativePath(result.filePaths[0]);
  });
  register("folder:add",1,(id)=>{if(imageEdits.busy)throw new Error("busy");if(!managedMode)throw new Error("unavailable");return folderImports.start(id);});
  register("folder:status",2,(id,job)=>folderImports.status(id,job));
  register("folder:stop",2,(id,job)=>folderImports.stop(id,job));
  const manual=()=>{if(folderImports.busy||imageEdits?.busy)throw new Error("busy");};
  register("ingestion:select", 1, (id) => {manual();return cataloging.choose(id);});
  register("ingestion:prepare", 3, (id, grant, recursive) => {manual();return cataloging.prepare(id, grant, recursive);});
  register("ingestion:status", 2, (id, operation) => cataloging.operation("ingestion.status", id, operation));
  register("ingestion:cancel", 2, (id, operation) => cataloging.operation("ingestion.cancel", id, operation));
  register("ingestion:apply", 3, (id, proposal, selection) => {manual();return cataloging.apply(id, proposal, selection);});
  register("ingestion:application-status", 2, (id, command) => cataloging.applicationStatus(id, command));
  register("ingestion:page", 4, (id, proposal, cursor, size) => cataloging.page(id, proposal, cursor, size));
  register("backend:retry", 0, async () => {
    if (recovering || libraries.isBusy) throw new Error("busy");
    if (!demo && libraries.current().state === "active") {
      try { return await libraries.query("gallery.list", libraries.current().session?.session_id, {page_size: 24, include_roots: true}); }
      catch (error) { if ((error as {code?: string}).code) throw error; }
    }
    if (libraries.isBusy) throw new Error("busy");
    recovering = true;
    libraries.invalidate();
    try {
      await backend.restart();
      if (!demo) await libraries.initialize();
      mainWindow?.webContents.send("backend:reset");
      return demo ? backend.request("gallery.list", {page_size: 24}) : libraries.query("gallery.list", libraries.current().session?.session_id, {page_size: 24, include_roots: true});
    } finally { recovering = false; }
  });
  if(managedMode){
    process.env.PLAYMEMORIES_DESKTOP_INGESTION_LAB="1";
    process.env.PLAYMEMORIES_DESKTOP_INDEX_STATE=join(app.getPath("userData"),"library-state","index-roots.json");
  }
  process.env.PLAYMEMORIES_DESKTOP_PROTECTED_PATHS = JSON.stringify([app.getPath("userData"), join(app.getPath("sessionData"), "Cache")]);
  if(managedSmoke && smokeDirectory)await preference.write({version:1,reopen:true,last:{path:join(smokeDirectory,"deleted-test.sqlite3"),handle:randomUUID()}});
  try { await backend.start(); if (!demo) await libraries.initialize(); }
  catch { libraries.invalidate(); }
  const window = createWindow();
  mainWindow = window;
  if(managedMode){indexer=new IndexCoordinator(backend,libraries,()=>!!folderImports?.busy||!!imageEdits?.busy,()=>window.webContents.send("gallery:changed"));indexer.start();}

  if (process.env.PLAYMEMORIES_DESKTOP_SMOKE === "1") {
    const watchdog = setTimeout(() => {
      console.error("SMOKE FAIL: timeout");
      process.exitCode = 1;
      app.quit();
    }, 45_000);
    window.webContents.once("render-process-gone", () => { process.exitCode = 1; app.quit(); });
    window.webContents.once("did-finish-load", () => {
      void smoke(window, backend, ingestionSmokeRoot ?? undefined).then(() => { clearTimeout(watchdog); app.quit(); }).catch((error: unknown) => {
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
  indexer?.dispose();
  void backend.stop().then(() => { if (smokeDirectory) rmSync(smokeDirectory, {recursive: true, force: true}); if (ingestionSmokeDirectory) rmSync(ingestionSmokeDirectory, {recursive: true, force: true}); app.exit(Number(process.exitCode ?? 0)); }).catch(() => { quitting = false; console.error("backend cleanup pending"); });
});
