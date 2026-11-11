// @vitest-environment jsdom
import {StrictMode,act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {FolderImportPanel} from "./FolderImportPanel";
let root:Root;let host:HTMLDivElement;
const job=(state="scanning",added_count=0)=>({job_id:"job",session_id:"session",state,added_count,excluded_count:1,error:null});
beforeEach(()=>{vi.useFakeTimers();Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});host=document.createElement("div");document.body.append(host);root=createRoot(host);window.photoManager={listGallery:vi.fn(),retryGallery:vi.fn(),addMediaFolder:vi.fn().mockResolvedValue(job()),getFolderImportStatus:vi.fn().mockResolvedValue(job("completed",125)),stopFolderImport:vi.fn().mockResolvedValue(job("stopped"))};});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();delete window.photoManager;vi.useRealTimers();});
it("admits once under effect replay and refreshes once after automatic completion",async()=>{
 const refresh=vi.fn();await act(async()=>root.render(<StrictMode><FolderImportPanel sessionId="session" onApplied={refresh}/></StrictMode>));
 expect(window.photoManager!.addMediaFolder).toHaveBeenCalledTimes(1);expect(host.textContent).not.toContain("Preparar proposta");
 await act(async()=>vi.advanceTimersByTimeAsync(1000));expect(refresh).toHaveBeenCalledTimes(1);expect(host.textContent).toContain("125 imagem(ns)");expect(host.textContent).toContain("Pasta carregada");expect(window.photoManager!.getFolderImportStatus).toHaveBeenCalledTimes(1);
});
it("cancelled selection does not poll or refresh",async()=>{
 window.photoManager!.addMediaFolder=vi.fn().mockResolvedValue(job("cancelled"));const refresh=vi.fn();await act(async()=>root.render(<FolderImportPanel sessionId="session" onApplied={refresh}/>));await act(async()=>vi.advanceTimersByTimeAsync(1000));expect(host.textContent).toContain("Seleção cancelada");expect(refresh).not.toHaveBeenCalled();expect(window.photoManager!.getFolderImportStatus).not.toHaveBeenCalled();
});
it("does not repeat admission after transport failure",async()=>{
 window.photoManager!.addMediaFolder=vi.fn().mockRejectedValue(new Error("private"));await act(async()=>root.render(<FolderImportPanel sessionId="session" onApplied={vi.fn()}/>));await act(async()=>vi.advanceTimersByTimeAsync(1000));expect(window.photoManager!.addMediaFolder).toHaveBeenCalledTimes(1);expect(host.querySelector('[role="alert"]')).not.toBeNull();expect(host.textContent).not.toContain("private");
});
it("rejects late results belonging to another session",async()=>{
 window.photoManager!.addMediaFolder=vi.fn().mockResolvedValue({...job("completed",1),session_id:"old"});const refresh=vi.fn();await act(async()=>root.render(<FolderImportPanel sessionId="session" onApplied={refresh}/>));expect(refresh).not.toHaveBeenCalled();expect(host.querySelector('[role="alert"]')).not.toBeNull();
});

it("explains that a covered subfolder belongs to the monitored parent", async () => {
  window.photoManager!.addMediaFolder = vi.fn().mockResolvedValue({...job("failed"), error: "covered_subfolder"});
  const refresh = vi.fn();
  await act(async () => root.render(<FolderImportPanel sessionId="session" onApplied={refresh} />));
  expect(host.querySelector('[role="status"]')?.textContent).toBe("Subpasta de uma pasta já cadastrada");
  expect(host.textContent).toContain("Atualizar pastas agora");
  expect(host.querySelector('[role="alert"]')).toBeNull();
  expect(refresh).not.toHaveBeenCalled();
});
