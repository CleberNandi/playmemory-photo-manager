import type {PythonBackend} from "./backend.js";
import type {LibraryController} from "./libraries.js";
export interface IndexStatus {state:string;busy:boolean;revision:number;added_count:number;error:string|null;last_check:number|null}
export class IndexCoordinator {
 private holds=0;private pending=false;private timer:ReturnType<typeof setInterval>|null=null;private session:string|null=null;
 private value:IndexStatus={state:"idle",busy:false,revision:0,added_count:0,error:null,last_check:null};
 constructor(private readonly backend:Pick<PythonBackend,"request">,private readonly libraries:Pick<LibraryController,"current"|"isBusy">,private readonly busy:()=>boolean,private readonly changed:()=>void){}
 current(){return this.libraries.current().session?.session_id===this.session?{...this.value}:{state:"idle",busy:false,revision:0,added_count:0,error:null,last_check:null};}
 private async pulse(allow:boolean){
  const id=this.libraries.current().session?.session_id;if(!id)return this.value;
  const result=await this.backend.request("index.pulse",{session_id:id,allow}) as IndexStatus;
  if(this.libraries.current().session?.session_id!==id)return this.value;
  const changed=this.session===id&&result.revision>this.value.revision;
  this.session=id;this.value=result;if(changed)this.changed();return result;
 }
 start(){if(this.timer)return;const tick=async()=>{if(this.pending)return;this.pending=true;try{await this.pulse(this.holds===0&&!this.busy()&&!this.libraries.isBusy);}catch{this.value={...this.value,state:"error",error:"unavailable"};}finally{this.pending=false;}};void tick();this.timer=setInterval(()=>void tick(),1000);this.timer.unref();}
 dispose(){if(this.timer)clearInterval(this.timer);this.timer=null;}
 async foreground<T>(action:()=>T|Promise<T>):Promise<T>{
  this.holds++;
  try{
   if(this.libraries.current().state==="active"){
    const deadline=Date.now()+35000;
    while((await this.pulse(false)).busy){if(Date.now()>deadline)throw new Error("busy");await new Promise(resolve=>setTimeout(resolve,100));}
   }
   return await action();
  }finally{this.holds--;}
 }
 async refresh(){const id=this.libraries.current().session?.session_id;if(!id)throw new Error("stale_session");await this.backend.request("index.refresh",{session_id:id});return this.current();}
}
