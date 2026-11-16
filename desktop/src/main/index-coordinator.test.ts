import {expect,it,vi} from "vitest";
import {IndexCoordinator} from "./index-coordinator.js";
import type {LibraryController} from "./libraries.js";
function fixture(){const status={state:"idle",busy:false,revision:0,added_count:0,error:null,last_check:null};const request=vi.fn().mockResolvedValue(status);const libraries:Pick<LibraryController,"current"|"isBusy">={isBusy:false,current:()=>({state:"active" as const,session:{session_id:"session",library_handle:"handle",display_name:"Test",generation:1},reopen:true})};const changed=vi.fn();const coordinator=new IndexCoordinator({request},libraries,()=>false,changed);return{status,request,coordinator,changed,libraries};}
it("pauses background work before admitting a foreground operation once",async()=>{const f=fixture();const action=vi.fn().mockResolvedValue("saved");expect(await f.coordinator.foreground(action)).toBe("saved");expect(f.request).toHaveBeenCalledWith("index.pulse",{session_id:"session",allow:false});expect(action).toHaveBeenCalledOnce();});
it("publishes catalog additions and keeps only one heartbeat in flight",async()=>{vi.useFakeTimers();const f=fixture();f.request.mockResolvedValueOnce(f.status).mockResolvedValue({...f.status,revision:1,added_count:1});f.coordinator.start();await vi.advanceTimersByTimeAsync(1100);expect(f.changed).toHaveBeenCalledOnce();expect(f.coordinator.current().added_count).toBe(1);f.coordinator.dispose();vi.useRealTimers();});
it("does not retry the user's mutation after a transport failure",async()=>{const f=fixture();const action=vi.fn().mockRejectedValue(Error("unknown"));await expect(f.coordinator.foreground(action)).rejects.toThrow("unknown");expect(action).toHaveBeenCalledOnce();});

it("refreshes the renderer even when the catalog revision is already current",async()=>{
 const f=fixture();
 await f.coordinator.refresh();
 expect(f.request).toHaveBeenCalledWith("index.refresh",{session_id:"session"});
 expect(f.changed).toHaveBeenCalledOnce();
 expect(f.coordinator.current().revision).toBe(0);
});

it("does not publish a refresh into a different library session",async()=>{
 const f=fixture();let finish!:(value:unknown)=>void;
 f.request.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 const result=f.coordinator.refresh();
 vi.spyOn(f.libraries,"current").mockReturnValue({state:"no_library",session:null,reopen:false});
 finish(f.status);
 await expect(result).rejects.toThrow("stale_session");
 expect(f.changed).not.toHaveBeenCalled();
});
