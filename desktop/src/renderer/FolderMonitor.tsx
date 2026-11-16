import {useEffect,useRef,useState} from "react";
const messages:Record<string,string>={root_changed:"Uma pasta mudou ou ficou indisponível. Confira o destino antes de adicioná-la novamente.",resource_limit:"Uma pasta excedeu os limites de leitura desta versão.",outcome_unknown:"Atualização interrompida com resultado a conferir. Reabra a biblioteca; não haverá repetição automática."};
export function FolderMonitor({onNotice}:{onNotice?:(notice:{text:string;error?:boolean})=>void}={}){
 const [status,setStatus]=useState<{state:string;error:string|null;added_count:number}|null>(null);
 const [failed,setFailed]=useState(false);
 const [refreshed,setRefreshed]=useState(false);
 const [dismissedError,setDismissedError]=useState<string|null>(null);
 const lastNotifiedError=useRef<string|null>(null);
 const noticeRef=useRef(onNotice);
 useEffect(()=>{noticeRef.current=onNotice;},[onNotice]);
 useEffect(()=>{
  if(!refreshed)return;
  if(noticeRef.current){noticeRef.current({text:"Pastas verificadas e atualizadas."});setRefreshed(false);return;}
  const timer=setTimeout(()=>setRefreshed(false),4500);
  return ()=>clearTimeout(timer);
 },[refreshed]);
 useEffect(()=>{let active=true;let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{try{const value=await window.photoManager?.getIndexStatus?.();if(active&&value){setStatus(value);setFailed(false);if(!value.error){setDismissedError(null);lastNotifiedError.current=null;}}}catch{if(active)setFailed(true);}if(active)timer=setTimeout(()=>void poll(),1000);};void poll();return ()=>{active=false;clearTimeout(timer);};
 },[]);
 const activeError=failed?"__poll_failed__":status?.error??null;
 useEffect(()=>{
  if(!activeError||!noticeRef.current)return;
  if(lastNotifiedError.current===activeError)return;
  lastNotifiedError.current=activeError;
  noticeRef.current({text:messages[activeError]??"Não foi possível atualizar uma pasta. A biblioteca continua disponível; confira permissões e disponibilidade.",error:true});
 },[activeError]);
 const showLocalError=Boolean(!onNotice&&activeError&&dismissedError!==activeError);
 return <section className="folder-monitor" aria-label="Atualização das pastas"><p role="status">{status?.state==="updating"?"Procurando novas imagens…":status?.state==="paused"?"Atualização aguardando sua operação":"Atualização automática das pastas ativa"}{status&&status.added_count>0?` · ${status.added_count} imagem(ns) nova(s)`:""}</p><button disabled={status?.state==="updating"} onClick={()=>{setFailed(false);setRefreshed(false);setDismissedError(null);lastNotifiedError.current=null;void window.photoManager?.refreshFolders?.().then(()=>setRefreshed(true)).catch(()=>setFailed(true));}}>Atualizar pastas agora</button>{!onNotice&&refreshed&&!failed&&!status?.error&&<div className="action-toast" role="status"><span>Pastas verificadas e atualizadas.</span><button type="button" className="toast-dismiss" aria-label="Fechar mensagem" onClick={()=>setRefreshed(false)}>×</button></div>}{showLocalError&&<div className="action-toast action-toast-error" role="alert"><span>{messages[activeError??""]??"Não foi possível atualizar uma pasta. A biblioteca continua disponível; confira permissões e disponibilidade."}</span><button type="button" className="toast-dismiss" aria-label="Fechar mensagem" onClick={()=>{setFailed(false);setDismissedError(activeError);}}>×</button></div>}</section>;
}
