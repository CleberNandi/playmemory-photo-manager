import {randomUUID} from "node:crypto";
import {expect,it,vi} from "vitest";
import {MediaActions} from "./media-actions.js";
function fixture(){
 const session=randomUUID(),asset=randomUUID();let current=session;
 const query=vi.fn().mockImplementation(async(method:string)=>method==="asset.reveal"?{path:"/synthetic/media/photo.jpg"}:{availability:"available",annotation:{favorite:false},asset:{kind:"photo"}});
 const choose=vi.fn().mockResolvedValue(null),reveal=vi.fn(),describe=vi.fn().mockResolvedValue(false);
 const libraries={query,current:()=>({state:"active" as const,session:{session_id:current,library_handle:randomUUID(),generation:1,display_name:"Synthetic"},reopen:true})};
 return {session,asset,query,choose,reveal,describe,switch:()=>{current=randomUUID();},actions:new MediaActions(libraries,choose,reveal,describe)};
}
it("returns only actions, and cancellation performs no external operation",async()=>{
 const f=fixture();expect(await f.actions.menu(f.session,f.asset)).toBeNull();expect(f.reveal).not.toHaveBeenCalled();expect(f.query).toHaveBeenCalledTimes(1);expect(f.choose.mock.calls[0][0].map((item:{action:string})=>item.action)).toEqual(["view","reveal","location","favorite","properties"]);
});
it("reveals only a backend-resolved path and never returns it to the renderer",async()=>{
 const f=fixture();f.choose.mockResolvedValue("reveal");expect(await f.actions.menu(f.session,f.asset)).toBeNull();expect(f.reveal).toHaveBeenCalledWith("/synthetic/media/photo.jpg");
 expect(await f.actions.locate(f.session,f.asset)).toEqual({status:"requested"});
});
it("rechecks the session after native dialogs and revalidates before reveal",async()=>{
 const f=fixture();f.describe.mockImplementation(async()=>{f.switch();return true;});await expect(f.actions.locate(f.session,f.asset,true)).rejects.toThrow("stale_session");expect(f.reveal).not.toHaveBeenCalled();
 const g=fixture();g.describe.mockResolvedValue(true);await g.actions.locate(g.session,g.asset,true);expect(g.query).toHaveBeenCalledTimes(2);expect(g.reveal).toHaveBeenCalledOnce();
});
it("rejects renderer paths, malicious backend paths and late menu actions",async()=>{
 const f=fixture();await expect(f.actions.locate(f.session,"/etc/passwd")).rejects.toThrow();expect(f.query).not.toHaveBeenCalled();
 f.query.mockResolvedValue({path:"../unsafe"});await expect(f.actions.locate(f.session,f.asset)).rejects.toThrow();expect(f.reveal).not.toHaveBeenCalled();
 const g=fixture();g.choose.mockImplementation(async()=>{g.switch();return "view";});await expect(g.actions.menu(g.session,g.asset)).rejects.toThrow("stale_session");
});
it("marks unavailable physical actions disabled while preserving catalog properties",async()=>{
 const f=fixture();f.query.mockResolvedValue({availability:"offline",annotation:null,asset:{kind:"photo"}});await f.actions.menu(f.session,f.asset);expect(f.choose.mock.calls[0][0].filter((item:{enabled:boolean})=>item.enabled).map((item:{action:string})=>item.action)).toEqual(["favorite","properties"]);
});
