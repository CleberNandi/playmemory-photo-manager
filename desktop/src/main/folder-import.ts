import {randomUUID} from "node:crypto";
import {lstat,realpath} from "node:fs/promises";
import type {PythonBackend} from "./backend.js";
import type {LibraryController} from "./libraries.js";
import {canonicalId,validPath} from "./library-preferences.js";
export interface FolderImportJob {job_id:string;session_id:string;state:"choosing"|"scanning"|"adding"|"completed"|"cancelled"|"stopped"|"failed"|"outcome_unknown";added_count:number;excluded_count:number;error:string|null}
const active=(job:FolderImportJob|null)=>!!job&&["choosing","scanning","adding"].includes(job.state);
const failure=(code:string):never=>{throw Object.assign(new Error(code),{code});};
const pause=()=>new Promise(resolve=>setTimeout(resolve,150));
export async function directoryIdentity(path:string):Promise<string>{
  if(!validPath(path)||await realpath(path)!==path)return failure("unsafe_location");
  const info=await lstat(path,{bigint:true});
  if(!info.isDirectory()||info.isSymbolicLink())return failure("unsafe_location");
  return `${info.dev}:${info.ino}`;
}
export class FolderImportController {
  private job:FolderImportJob|null=null;
  private stopped=false;
  get busy(){return active(this.job);}
  constructor(private readonly backend:Pick<PythonBackend,"request">,private readonly libraries:Pick<LibraryController,"current"|"isBusy">,private readonly windowId:string,private readonly choose:()=>Promise<string|null>,private readonly identity=directoryIdentity){}
  private require(session:unknown):string{
    if(this.libraries.isBusy)return failure("busy");
    const state=this.libraries.current();
    if(!canonicalId(session)||state.state!=="active"||state.session?.session_id!==session)return failure("stale_session");
    return session;
  }
  start(session:unknown):FolderImportJob{
    const id=this.require(session);
    if(this.busy){if(this.job!.session_id!==id)return failure("busy");return structuredClone(this.job!);}
    this.stopped=false;
    const job:FolderImportJob={job_id:randomUUID(),session_id:id,state:"choosing",added_count:0,excluded_count:0,error:null};
    this.job=job;
    void this.run(job);
    return structuredClone(job);
  }
  status(session:unknown,id:unknown):FolderImportJob{
    this.require(session);
    if(!canonicalId(id)||this.job?.job_id!==id||this.job.session_id!==session)return failure("not_found");
    return structuredClone(this.job);
  }
  stop(session:unknown,id:unknown):FolderImportJob{const job=this.status(session,id);this.stopped=true;return job;}
  private async send(job:FolderImportJob,method:Parameters<PythonBackend["request"]>[0],params:Record<string,unknown>){
    this.require(job.session_id);
    const value=await this.backend.request(method,{...params,session_id:job.session_id,window_id:this.windowId});
    this.require(job.session_id);
    return value;
  }
  private async run(job:FolderImportJob){
    let applying=false;
    try{
      const path=await this.choose();
      this.require(job.session_id);
      if(path===null){job.state="cancelled";return;}
      const binding=await this.identity(path);
      // One native choice authorizes this finite job, not a persistent watcher.
      for(let batch=0;batch<21;batch++){
        if(this.stopped){job.state="stopped";return;}
        if(await this.identity(path)!==binding)return failure("root_changed");
        job.state="scanning";
        const grant=await this.send(job,"ingestion.select_root",{path,recursive:true,identity_reviewed:true}) as {root_grant_id:string};
        if(await this.identity(path)!==binding)return failure("root_changed");
        let preparation=await this.send(job,"ingestion.prepare",{root_grant_id:grant.root_grant_id,recursive:true,client_request_id:randomUUID()}) as {operation_id:string;state:string;proposal_id:string|null;excluded_count:number;terminal_reason?:string};
        const deadline=Date.now()+45000;
        let cancelSent=false;
        while(!["completed","failed","cancelled"].includes(preparation.state)){
          if(Date.now()>deadline)return failure("resource_limit");
          if(this.stopped&&!cancelSent){await this.send(job,"ingestion.cancel",{operation_id:preparation.operation_id});cancelSent=true;}
          await pause();
          const next=await this.send(job,"ingestion.status",{operation_id:preparation.operation_id}) as typeof preparation;
          if(next.operation_id!==preparation.operation_id)return failure("stale_session");
          preparation=next;
        }
        if(this.stopped){job.state="stopped";return;}
        if(preparation.state!=="completed"||!canonicalId(preparation.proposal_id))return failure(preparation.terminal_reason??"unavailable");
        job.excluded_count=preparation.excluded_count;
        const ids:string[]=[];
        let cursor:string|null=null;
        for(let page=0;page<40;page++){
          const result=await this.send(job,"ingestion.page",{proposal_id:preparation.proposal_id,cursor,page_size:50}) as {next_cursor:string|null;items:{candidate_id:string;selectable?:boolean}[]};
          for(const item of result.items)if(item.selectable&&ids.length<100)ids.push(item.candidate_id);
          if(ids.length===100||!result.next_cursor)break;
          cursor=result.next_cursor;
        }
        if(!ids.length){job.state="completed";return;}
        if(ids.some(id=>!canonicalId(id))||new Set(ids).size!==ids.length)return failure("invalid_request");
        if(await this.identity(path)!==binding)return failure("root_changed");
        if(this.stopped){job.state="stopped";return;}
        job.state="adding";applying=true;
        let command=await this.send(job,"ingestion.apply",{proposal_id:preparation.proposal_id,candidate_ids:ids,client_request_id:randomUUID()}) as {command_id:string;state:string;result:{status:string;items:{disposition:string}[]}|null};
        const until=Date.now()+45000;
        while(["queued","running"].includes(command.state)){
          if(Date.now()>until)return failure("outcome_unknown");
          await pause();
          const next=await this.send(job,"ingestion.application_status",{command_id:command.command_id}) as typeof command;
          if(next.command_id!==command.command_id)return failure("outcome_unknown");
          command=next;
        }
        if(command.state==="outcome_unknown")return failure("outcome_unknown");
        if(command.state!=="completed"||command.result?.status!=="applied")return failure("catalog_changed");
        job.added_count+=command.result.items.filter(item=>item.disposition==="created").length;
        applying=false;
      }
      return failure("resource_limit");
    }catch(error){
      const code=(error as {code?:string}).code;
      const allowed=["busy","root_changed","unsafe_location","permission_denied","resource_limit","stale_session","not_found","catalog_changed","outcome_unknown"];
      job.error=code&&allowed.includes(code)?code:applying?"outcome_unknown":"unavailable";
      job.state=job.error==="outcome_unknown"?"outcome_unknown":"failed";
    }
  }
}
