import {randomUUID} from "node:crypto";
import {expect,it,vi,afterEach} from "vitest";
import {FolderImportController} from "./folder-import.js";
const session=randomUUID(),windowId=randomUUID();
function fixture(count=125){
 let current=session;let selected:string[]=[];const created=new Set<string>();const ids=Array.from({length:count},()=>randomUUID());
 const libraries={isBusy:false,current:()=>({state:"active" as const,session:{session_id:current,library_handle:randomUUID(),generation:1,display_name:"Synthetic"},reopen:true})};
 const choose=vi.fn().mockResolvedValue("/synthetic/media");const identity=vi.fn().mockResolvedValue("1:2");
 const request=vi.fn(async(method:string,p:Record<string,unknown>)=>{
  if(method==="ingestion.select_root")return {root_grant_id:randomUUID()};
  if(method==="ingestion.prepare")return {operation_id:randomUUID(),state:"completed",proposal_id:randomUUID(),excluded_count:3};
  if(method==="ingestion.page"){const start=Number(p.cursor??0);return {items:ids.slice(start,start+50).map(candidate_id=>({candidate_id,selectable:!created.has(candidate_id)})),next_cursor:start+50<count?String(start+50):null};}
  if(method==="ingestion.apply"){selected=p.candidate_ids as string[];selected.forEach(id=>created.add(id));return {command_id:randomUUID(),state:"completed",result:{status:"applied",items:selected.map(()=>({disposition:"created"}))}};}
  throw new Error("unexpected method");
 });
 const controller=new FolderImportController({request},libraries,windowId,choose,identity);
 return {controller,request,choose,identity,created,setSession:()=>{current=randomUUID();}};
}
async function finished(f:ReturnType<typeof fixture>,id:string){for(let i=0;i<100;i++){await Promise.resolve();const job=f.controller.status(session,id);if(!["choosing","scanning","adding"].includes(job.state))return job;}throw new Error("job did not finish");}
afterEach(()=>vi.useRealTimers());
it("one selection loads all supported candidates in bounded batches without exposing paths",async()=>{
 const f=fixture();const job=f.controller.start(session);const result=await finished(f,job.job_id);
 expect(result.state).toBe("completed");expect(result.added_count).toBe(125);expect(f.choose).toHaveBeenCalledOnce();
 expect(f.request.mock.calls.filter(([method])=>method==="ingestion.apply").map(([,p])=>(p.candidate_ids as string[]).length)).toEqual([100,25]);
 expect(f.created.size).toBe(125);expect(JSON.stringify(result)).not.toContain("/synthetic");
 expect(f.request.mock.calls.every(([,p])=>p.session_id===session&&p.window_id===windowId)).toBe(true);
});
it("cancels the native picker without preparation or writes",async()=>{
 const f=fixture();f.choose.mockResolvedValue(null);const job=f.controller.start(session);expect((await finished(f,job.job_id)).state).toBe("cancelled");expect(f.request).not.toHaveBeenCalled();
});
it("deduplicates repeat admission while the same folder dialog is open",async()=>{
 const f=fixture();let resolve!:(p:string|null)=>void;f.choose.mockImplementation(()=>new Promise(done=>{resolve=done;}));const first=f.controller.start(session);expect(f.controller.start(session).job_id).toBe(first.job_id);expect(f.choose).toHaveBeenCalledOnce();resolve(null);await finished(f,first.job_id);
});
it("rejects a root replacement before authorizing the next batch",async()=>{
 const f=fixture();f.identity.mockResolvedValueOnce("1:2").mockResolvedValue("3:4");const job=f.controller.start(session);expect((await finished(f,job.job_id)).error).toBe("root_changed");expect(f.request).not.toHaveBeenCalled();
});
it("does not retry a mutation with a lost acknowledgement",async()=>{
 const f=fixture();const original=f.request.getMockImplementation()!;f.request.mockImplementation(async(method,p)=>{if(method==="ingestion.apply")throw new Error("private details");return original(method,p);});const job=f.controller.start(session);const result=await finished(f,job.job_id);expect(result.state).toBe("outcome_unknown");expect(f.request.mock.calls.filter(([method])=>method==="ingestion.apply")).toHaveLength(1);expect(JSON.stringify(result)).not.toContain("private");
});
it("stops before admitting work and rejects an invalid session",async()=>{
 const f=fixture();expect(()=>f.controller.start(randomUUID())).toThrow("stale_session");const job=f.controller.start(session);f.controller.stop(session,job.job_id);expect((await finished(f,job.job_id)).state).toBe("stopped");expect(f.request).not.toHaveBeenCalled();
});
