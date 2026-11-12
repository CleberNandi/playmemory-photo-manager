import {useEffect,useRef,useState} from "react";
interface Job {job_id:string;session_id:string;state:string;added_count:number;excluded_count:number;error:string|null;covered_folder?:{root_id:string;relative_path:string}}
const running=(job:Job)=>["choosing","scanning","adding"].includes(job.state);
const messages:Record<string,string>={resource_limit:"Esta pasta excedeu os limites desta versão. Adicione uma subpasta menor.",root_changed:"A pasta mudou durante a leitura. Selecione-a novamente.",unsafe_location:"Escolha uma pasta de imagens separada do catálogo e dos dados do aplicativo.",permission_denied:"Sem permissão para ler esta pasta.",catalog_changed:"A biblioteca mudou durante a carga. As imagens já adicionadas foram preservadas.",outcome_unknown:"Não foi possível confirmar o último lote. Reabra a biblioteca para conferir; nenhum pedido será repetido automaticamente.",busy:"Há outra operação em andamento. Aguarde sua conclusão.",stale_session:"A biblioteca mudou. Adicione a pasta novamente na biblioteca atual."};
export function FolderImportPanel({sessionId,onApplied,onOpenFolder,onDismiss}: {sessionId:string;onApplied:()=>void;onOpenFolder?:(id:string,path:string)=>void;onDismiss?:()=>void}){
 const [job,setJob]=useState<Job|null>(null);
 const [error,setError]=useState(false);
 const [stopping,setStopping]=useState(false);
 const admission=useRef<Promise<unknown>|null>(null);
 const notified=useRef(false);
 const callback=useRef(onApplied);
 useEffect(()=>{callback.current=onApplied;},[onApplied]);
 const accept=(value:Job)=>{
   if(value.session_id!==sessionId||typeof value.job_id!=="string")throw new Error();
   setJob(value);
   if(!running(value)&&!notified.current&&(value.state==="completed"||value.state==="stopped"||value.added_count>0)){notified.current=true;callback.current();}
 };
 useEffect(()=>{
   let active=true;
   admission.current??=window.photoManager!.addMediaFolder!(sessionId);
   void admission.current.then(value=>{if(active)accept(value as Job);}).catch(()=>{if(active)setError(true);});
   return ()=>{active=false;};
   // One explicit Add folder action owns this admission, even under effect replay.
   // eslint-disable-next-line react-hooks/exhaustive-deps
 },[sessionId]);
 useEffect(()=>{
   if(!job||!running(job))return;
   let disposed=false;let timer:ReturnType<typeof setTimeout>;
   const poll=async()=>{try{const value=await window.photoManager!.getFolderImportStatus!(sessionId,job.job_id) as Job;if(!disposed){if(value.job_id!==job.job_id)throw new Error();accept(value);if(running(value))timer=setTimeout(()=>void poll(),250);}}catch{if(!disposed)setError(true);}};
   timer=setTimeout(()=>void poll(),250);return ()=>{disposed=true;clearTimeout(timer);};
   // A single non-overlapping polling loop owns this job.
   // eslint-disable-next-line react-hooks/exhaustive-deps
 },[sessionId,job?.job_id]);
 const covered=job?.error==="covered_subfolder";
 const label=covered?"Subpasta de uma pasta já cadastrada":job?.state==="choosing"?"Escolha uma pasta de imagens…":job?.state==="scanning"?"Examinando a pasta…":job?.state==="adding"?"Adicionando imagens…":job?.state==="completed"?"Pasta carregada":job?.state==="cancelled"?"Seleção cancelada":job?.state==="stopped"?"Carga interrompida":job?.state==="outcome_unknown"?"Resultado a conferir":job?.state==="failed"?"Não foi possível concluir a carga":"Abrindo seletor de pasta…";
 return <section className="folder-import-panel" aria-label="Adicionar pasta" aria-busy={!job||running(job)}>
   <div className="folder-import-heading"><strong role="status">{label}</strong>
     {job&&!running(job)&&onDismiss&&<button className="primary-button" onClick={onDismiss}>Fechar aviso</button>}
   </div>
   {covered&&<p>A pasta principal já é acompanhada com suas subpastas. Use Atualizar pastas agora para verificar as imagens.</p>}
   {covered&&job.covered_folder&&onOpenFolder&&<button className="primary-button" onClick={() => {
      const folder=job.covered_folder!;
      onOpenFolder(folder.root_id,folder.relative_path);
   }}>Abrir pasta no catálogo</button>}
   {job&&!covered&&<p>{job.added_count} imagem(ns) adicionada(s) · {job.excluded_count} entrada(s) fora do suporte. Os originais permanecem inalterados.</p>}
   {job?.state==="completed"&&job.added_count===0&&<p>As imagens aceitas já podem estar na biblioteca; arquivos sem suporte não são adicionados.</p>}
   {(error||(job?.error&&!covered))&&<p role="alert">{job?.error?messages[job.error]??"A carga foi interrompida. Selecione a pasta novamente para conferir os itens restantes.":"A conexão foi interrompida. Reabra a biblioteca para conferir os itens adicionados."}</p>}
   {job&&running(job)&&job.state!=="choosing"&&<button disabled={stopping} onClick={()=>{setStopping(true);void window.photoManager!.stopFolderImport!(sessionId,job.job_id).catch(()=>setError(true));}}>{stopping?"Parando após o lote atual…":"Parar carga"}</button>}
 </section>;
}
