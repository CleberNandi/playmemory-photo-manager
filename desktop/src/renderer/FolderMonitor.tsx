import {useEffect,useState} from "react";
export function FolderMonitor(){
 const [status,setStatus]=useState<{state:string;error:string|null;added_count:number}|null>(null);
 const [failed,setFailed]=useState(false);
 useEffect(()=>{let active=true;let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{try{const value=await window.photoManager?.getIndexStatus?.();if(active&&value){setStatus(value);setFailed(false);}}catch{if(active)setFailed(true);}if(active)timer=setTimeout(()=>void poll(),1000);};void poll();return ()=>{active=false;clearTimeout(timer);};
 },[]);
 const messages:Record<string,string>={root_changed:"Uma pasta mudou ou ficou indisponível. Confira o destino antes de adicioná-la novamente.",resource_limit:"Uma pasta excedeu os limites de leitura desta versão.",outcome_unknown:"Atualização interrompida com resultado a conferir. Reabra a biblioteca; não haverá repetição automática."};
 return <section className="folder-monitor" aria-label="Atualização das pastas"><p role="status">{status?.state==="updating"?"Procurando novas imagens…":status?.state==="paused"?"Atualização aguardando sua operação":"Atualização automática das pastas ativa"}{status&&status.added_count>0?` · ${status.added_count} imagem(ns) nova(s)`:""}</p><button disabled={status?.state==="updating"} onClick={()=>{setFailed(false);void window.photoManager?.refreshFolders?.().catch(()=>setFailed(true));}}>Atualizar pastas agora</button>{(failed||status?.error)&&<p role="alert">{messages[status?.error??""]??"Não foi possível atualizar uma pasta. A biblioteca continua disponível; confira permissões e disponibilidade."}</p>}</section>;
}
