import {randomUUID} from "node:crypto";
import type {LibraryController} from "./libraries.js";
import {canonicalId,validPath} from "./library-preferences.js";
type Mode="replace"|"copy";
export interface EditJob {job_id:string;asset_id:string;state:string;result_asset_id:string|null;error:string|null}
export class ImageEdits {
 private job:EditJob|null=null;
 get busy(){return !!this.job&&["choosing","confirming","running"].includes(this.job.state);}
 constructor(private readonly libraries:Pick<LibraryController,"current"|"query">,private readonly choose:(source:string,angle:number)=>Promise<string|null>,private readonly confirm:(source:string,angle:number)=>Promise<boolean>){}
 private check(session:unknown,asset:unknown){if(!canonicalId(session)||!canonicalId(asset)||this.libraries.current().session?.session_id!==session)throw new Error("stale_session");}
 start(session:unknown,asset:unknown,angle:unknown,mode:unknown){
  this.check(session,asset);if(this.busy)throw new Error("busy");
  if(typeof angle!=="number"||![90,180,270].includes(angle)||(mode!=="replace"&&mode!=="copy"))throw new Error("invalid_request");
  const job:EditJob={job_id:randomUUID(),asset_id:asset as string,state:mode==="copy"?"choosing":"confirming",result_asset_id:null,error:null};this.job=job;
  void this.run(job,session,angle,mode);return {...job};
 }
 status(session:unknown,id:unknown){this.check(session,this.job?.asset_id);if(!canonicalId(id)||id!==this.job?.job_id)throw new Error("not_found");return {...this.job};}
 private async run(job:EditJob,session:unknown,angle:number,mode:Mode){
  let admitted=false;
  try{
   const source=await this.libraries.query("asset.reveal",session,{asset_id:job.asset_id}) as {path:string};this.check(session,job.asset_id);if(!validPath(source.path))throw new Error("unavailable");
   const target=mode==="copy"?await this.choose(source.path,angle):null;
   if((mode==="copy"&&target===null)||(mode==="replace"&&!await this.confirm(source.path,angle))){job.state="cancelled";return;}
   this.check(session,job.asset_id);job.state="running";admitted=true;
   let result=await this.libraries.query("image.save",session,{asset_id:job.asset_id,angle,mode,target,request_id:job.job_id}) as EditJob;
   const deadline=Date.now()+25000;
   while(result.state==="running"){
    if(Date.now()>deadline)throw new Error("outcome_unknown");
    await new Promise(resolve=>setTimeout(resolve,200));
    result=await this.libraries.query("image.save_status",session,{job_id:job.job_id}) as EditJob;
   }
   this.check(session,job.asset_id);if(result.job_id!==job.job_id||result.asset_id!==job.asset_id)throw new Error("outcome_unknown");
   Object.assign(job,result);
  }catch(error){const code=(error as {code?:string}).code;const known=["already_exists","unsafe_location","unsupported_format","busy","invalid_request","not_found","permission_denied"];
   job.error=code&&known.includes(code)?code:admitted?"outcome_unknown":"unavailable";job.state=job.error==="outcome_unknown"?"outcome_unknown":"failed";
  }
 }
}
