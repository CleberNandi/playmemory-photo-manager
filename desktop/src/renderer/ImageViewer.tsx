import {useEffect,useRef,useState} from "react";
import {requestThumbnail} from "./thumbnails";
import {readOriginal} from "./image-data";
import type {ImageSaveJob} from "./types";
export function viewerGeometry(width:number,height:number,rotation:number,zoom:number,viewportWidth:number,viewportHeight:number){
 const sideways=rotation%180!==0;
 const rotatedWidth=sideways?height:width,rotatedHeight=sideways?width:height;
 const scale=zoom?zoom/100:Math.min(1,Math.max(1,viewportWidth-24)/Math.max(1,rotatedWidth),Math.max(1,viewportHeight-24)/Math.max(1,rotatedHeight));
 return {width:width*scale,height:height*scale,boxWidth:rotatedWidth*scale,boxHeight:rotatedHeight*scale};
}
export type ViewerFrame = {id:string; name:string};

function FilmFrame({frame, selected, onClick}: {frame:ViewerFrame; selected:boolean; onClick:()=>void}) {
  const [url,setUrl]=useState<string|null>(null);
  useEffect(()=>requestThumbnail(frame.id,setUrl),[frame.id]);
  return <button type="button" title={frame.name} aria-label={frame.name}
    aria-current={selected?"true":undefined} onClick={onClick}>
    {url?<img src={url} alt="" />:<span>{frame.name}</span>}
  </button>;
}

export function ImageViewer({assetId,onClose,restoreFocus,initialRotation=0,name="Imagem selecionada",position,onPrevious,onNext,onSaved,frames,onFrame,loadingNext=false,nextError=false,canSave=true}: {assetId:string;onClose:()=>void;restoreFocus?:()=>void;initialRotation?:number;name?:string;position?:string;onPrevious?:()=>void;onNext?:()=>void;frames?:ViewerFrame[];onFrame?:(id:string)=>void;loadingNext?:boolean;nextError?:boolean;canSave?:boolean;onSaved?:(mode:"replace"|"copy",assetId:string)=>void}) {
 const activeFrame=frames?.findIndex(frame=>frame.id===assetId)??-1;
 const [saving,setSaving]=useState(false);
 const [saveMessage,setSaveMessage]=useState<{id:string;text:string}|null>(null);
 const [uncertain,setUncertain]=useState(false);
 const [leaving,setLeaving]=useState<{action:()=>void}|null>(null);
 const inFlight=useRef(false),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return ()=>{mounted.current=false;};},[]);
 const [image,setImage]=useState<{id:string;url:string}|null>(null);
 const [original,setOriginal]=useState<{id:string;attempt:number;url:string|null}|null>(null);
 const [failure,setFailure]=useState<string|null>(null);
 const [dimensions,setDimensions]=useState<{id:string;url:string;width:number;height:number}|null>(null);
 const [view,setView]=useState({id:assetId,zoom:0,rotation:initialRotation});
 const [retry,setRetry]=useState({id:assetId,value:0});
 const [viewport,setViewport]=useState({width:1280,height:960});
 const unsaved=useRef<HTMLElement>(null);
 const closeButton=useRef<HTMLButtonElement>(null);
 useEffect(()=>{if(leaving)unsaved.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();},[leaving]);
 const dialog=useRef<HTMLDialogElement>(null),canvas=useRef<HTMLDivElement>(null);
 const rotation=view.id===assetId?view.rotation:initialRotation,zoom=view.id===assetId?view.zoom:0;
 const attempt=retry.id===assetId?retry.value:0;
 const preview=image?.id===assetId?image.url:null;
 const full=original?.id===assetId&&original.attempt===attempt?original:null;
 const showingOriginal=!!(zoom&&full?.url);
 const url=showingOriginal?full!.url:preview;
 const size=dimensions?.id===assetId&&dimensions.url===url?dimensions:null;
 const wantsOriginal=zoom!==0;
 const failed=failure===assetId;
 if(view.id!==assetId)setView({id:assetId,zoom:0,rotation:initialRotation});
 const update=(next:{zoom?:number;rotation?:number})=>setView({id:assetId,zoom,rotation,...next});
 const leave=(action:(()=>void)|undefined)=>{if(!action||saving)return;if(rotation!==0)setLeaving({action});else action();};
 const save=async(mode:"replace"|"copy")=>{
  if(inFlight.current||!rotation||uncertain||!window.photoManager?.saveRotation||!canSave)return;
  inFlight.current=true;setSaving(true);setSaveMessage(null);
  const continuation=leaving?.action;setLeaving(null);
  try{
   let result=await window.photoManager.saveRotation(assetId,rotation,mode);
   const jobId=result.job_id;
   const validate=(job:ImageSaveJob)=>{if(job.asset_id!==assetId||job.job_id!==jobId)throw new Error();};validate(result);
   while(mounted.current&&["choosing","confirming","running"].includes(result.state)){
    await new Promise(resolve=>setTimeout(resolve,250));if(!mounted.current)return;
    result=await window.photoManager!.getImageSaveStatus!(jobId);validate(result);
   }
   if(!mounted.current)return;
   if(result.state==="completed"&&result.result_asset_id){
    update({rotation:0});setImage(null);setRetry({id:assetId,value:attempt+1});
    setSaveMessage({id:assetId,text:mode==="copy"?"Cópia salva e adicionada à biblioteca. O original foi preservado.":"Alterações salvas no arquivo original."});
    onSaved?.(mode,result.result_asset_id);continuation?.();
   }else if(result.state==="cancelled"){setSaveMessage({id:assetId,text:"Gravação cancelada. A rotação ainda não foi salva."});}
   else {
    const messages:Record<string,string>={already_exists:"Esse nome já existe. Escolha outro nome para a cópia.",unsafe_location:"O arquivo mudou ou o destino não é seguro. Para copiar, escolha um nome novo na mesma pasta do original. Substituição de hardlinks ou múltiplas ocorrências não é permitida.",unsupported_format:"Gravação disponível para PNG e JPEG de uma única imagem.",outcome_unknown:"Não foi possível confirmar a gravação. Reabra a biblioteca e confira o arquivo antes de editar novamente; não haverá repetição automática."};
    if(result.state==="outcome_unknown")setUncertain(true);
    setSaveMessage({id:assetId,text:messages[result.error??""]??"Não foi possível salvar. A rotação continua pendente; nenhum pedido será repetido automaticamente."});
   }
  }catch{if(mounted.current){setUncertain(true);setSaveMessage({id:assetId,text:"A conexão foi interrompida. Reabra a biblioteca e confira o arquivo antes de editar novamente; não haverá repetição automática."});}}
  finally{inFlight.current=false;if(mounted.current)setSaving(false);}
 };
 const rotate=(delta:number)=>update({rotation:(rotation+delta+360)%360});
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;dialog.current?.showModal();return ()=>{if(restoreFocus)restoreFocus();else previous?.focus({preventScroll:true});};},[restoreFocus]);
 useEffect(()=>{const node=dialog.current;if(node?.open&&!node.contains(document.activeElement))closeButton.current?.focus({preventScroll:true});},[assetId]);
 useEffect(()=>{
  const node=canvas.current;if(!node)return;
  const measure=()=>setViewport({width:node.clientWidth,height:node.clientHeight});measure();
  if(typeof ResizeObserver==="undefined")return;
  const observer=new ResizeObserver(measure);observer.observe(node);return ()=>observer.disconnect();
 },[]);
 useEffect(()=>{
  let active=true;
  void (async()=>{
   const deadline=Date.now()+12000;
   try{
    while(active){
     const value=await window.photoManager?.getPreview?.(assetId) as {status?:string;media_type?:string;base64?:string}|null;
     if(!active)return;
     if(value?.status==="pending"&&Date.now()<deadline){await new Promise(resolve=>setTimeout(resolve,150));continue;}
     if(value?.media_type!=="image/jpeg"||typeof value.base64!=="string"||value.base64.length>220000||!/^\/9j\/[A-Za-z0-9+/]*={0,2}$/.test(value.base64)||value.base64.length%4!==0)throw new Error();
     setImage({id:assetId,url:`data:image/jpeg;base64,${value.base64}`});setFailure(null);return;
    }
   }catch{if(active)setFailure(assetId);}
  })();return ()=>{active=false;};
 },[assetId,attempt]);
 useEffect(()=>{
  const keyboard=(event:KeyboardEvent)=>{
   if(saving||leaving||!dialog.current?.open||event.altKey||event.ctrlKey||event.metaKey)return;
   if(event.key!=="ArrowLeft"&&event.key!=="ArrowRight")return;
   event.preventDefault();event.stopPropagation();if(event.key==="ArrowLeft")leave(onPrevious);else if(!loadingNext)leave(onNext);
  };
  document.addEventListener("keydown",keyboard);return ()=>document.removeEventListener("keydown",keyboard);
 // The current edit and leave guard belong to the active viewer frame.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[onPrevious,onNext,rotation,saving,leaving,loadingNext]);
 useEffect(()=>{
  if(!wantsOriginal)return;
  let active=true;
  void readOriginal(assetId,()=>active)
   .then(url=>{if(active)setOriginal({id:assetId,attempt,url});})
   .catch(()=>{if(active)setOriginal({id:assetId,attempt,url:null});});
  return ()=>{active=false;};
 },[assetId,attempt,wantsOriginal]);
 const geometry=size?viewerGeometry(size.width,size.height,rotation,showingOriginal?zoom:0,viewport.width,viewport.height):null;
 return <dialog className="image-viewer" ref={dialog} aria-label="Visualizar imagem" onKeyDown={event=>{
  if(event.key==="Escape"){event.stopPropagation();return;}

 }} onCancel={event=>{event.preventDefault();if(leaving)setLeaving(null);else leave(onClose);}}>
  <header inert={!!leaving} className="viewer-toolbar">
   <div className="viewer-title">
    <button className="viewer-icon" data-icon="←" ref={closeButton} autoFocus disabled={saving} onClick={()=>leave(onClose)}
      aria-label="Fechar imagem" title="Voltar à biblioteca"><span className="sr-only">Fechar imagem</span></button>
    <p className="viewer-caption" role="status"><strong className="viewer-filename">{name}</strong>{position?` · ${position}`:""} · {rotation}°{showingOriginal&&size?` · ${size.width} × ${size.height} px · ${zoom}%`:""}</p>
   </div>
  </header>
  {leaving&&<section ref={unsaved} className="viewer-unsaved" role="alertdialog" aria-modal="true" aria-label="Rotação não salva"><strong>Salvar a rotação antes de sair desta imagem?</strong><button disabled={!window.photoManager?.saveRotation||uncertain||!canSave} onClick={()=>void save("replace")}>Salvar alterações e continuar</button><button disabled={!window.photoManager?.saveRotation||uncertain||!canSave} onClick={()=>void save("copy")}>Salvar cópia e continuar</button><button onClick={()=>{const action=leaving.action;setLeaving(null);update({rotation:0});action();}}>Descartar rotação</button><button onClick={()=>{setLeaving(null);closeButton.current?.focus();}}>Continuar editando</button></section>}
  {saving&&<p className="viewer-caption" role="status">Salvando imagem em resolução original… Aguarde a conclusão.</p>}
  {saveMessage?.id===assetId&&<p className="viewer-caption" role="status">{saveMessage.text}</p>}
  {wantsOriginal&&!showingOriginal&&<p className="viewer-caption" role="status">{full?"Resolução original indisponível. Exibindo prévia ajustada.":"Carregando resolução original…"}</p>}
  {loadingNext&&<p className="viewer-caption" role="status">Carregando próximas imagens…</p>}
  {nextError&&<p className="viewer-caption" role="status">Falha ao carregar próximas imagens. Use a seta para tentar novamente.</p>}
  <div className="viewer-surface" inert={!!leaving}>
  <button className="viewer-edge viewer-edge-prev" data-icon="‹" aria-label="Imagem anterior" title="Anterior (←)" disabled={saving||!onPrevious} hidden={!onPrevious} onClick={()=>{if(onPrevious)leave(onPrevious);}}>
    <span className="sr-only">Anterior</span>
  </button>
  <button className="viewer-edge viewer-edge-next" data-icon="›" aria-label="Próxima imagem" title="Próxima (→)" disabled={saving||loadingNext||!onNext} hidden={!onNext} onClick={()=>{if(onNext)leave(onNext);}}>
    <span className="sr-only">Próxima</span>
  </button>
  <div ref={canvas} inert={!!leaving} className={`viewer-image${showingOriginal?" viewer-zoomed":""}`}>
   {url?<div className="viewer-stage" style={geometry?{width:geometry.boxWidth,height:geometry.boxHeight}:undefined}><img key={assetId} src={url} alt={showingOriginal?name:`Prévia de ${name}`} onLoad={event=>setDimensions({id:assetId,url,width:event.currentTarget.naturalWidth,height:event.currentTarget.naturalHeight||1})} onError={()=>{if(showingOriginal)setOriginal({id:assetId,attempt,url:null});else{setImage(null);setFailure(assetId);}}} style={geometry?{width:`${geometry.width}px`,height:`${geometry.height}px`,maxWidth:"none",maxHeight:"none",transform:`translate(-50%, -50%) rotate(${rotation}deg)`}:{transform:`rotate(${rotation}deg)`}}/></div>:failed?<div role="alert"><p>Prévia indisponível. O arquivo pode estar offline, ter mudado ou não ser decodificável dentro dos limites.</p><button onClick={()=>{setFailure(null);setRetry({id:assetId,value:attempt+1});}}>Tentar prévia novamente</button></div>:<p role="status">Preparando prévia…</p>}
  </div>
  </div>
  <footer className="viewer-tools" inert={!!leaving}>
   <div className="viewer-controls" role="toolbar" aria-label="Controles da imagem">
    <div className="viewer-control-group" aria-label="Zoom"><button onClick={()=>update({zoom:0})}>Ajustar</button><button onClick={()=>update({zoom:100})}>100%</button><button aria-label="Ampliar imagem" onClick={()=>update({zoom:Math.min(200,(zoom||100)+25)})}>+</button><button aria-label="Reduzir imagem" onClick={()=>update({zoom:Math.max(25,(zoom||100)-25)})}>−</button></div>
    <div className="viewer-control-group" aria-label="Rotação"><button disabled={!url||saving||loadingNext} onClick={()=>rotate(-90)}>Girar à esquerda</button><button disabled={!url||saving||loadingNext} onClick={()=>rotate(90)}>Girar à direita</button><button disabled={rotation===0||saving} onClick={()=>update({rotation:0})}>Restaurar rotação</button></div>
    {rotation!==0&&canSave&&<div className="viewer-control-group viewer-save-group" aria-label="Gravação"><button disabled={saving||uncertain||!rotation||!window.photoManager?.saveRotation||!canSave} onClick={()=>void save("replace")}>Salvar alterações</button><button disabled={saving||uncertain||!rotation||!window.photoManager?.saveRotation||!canSave} onClick={()=>void save("copy")}>Salvar como cópia</button></div>}
   </div>
   <p className="viewer-hint">Ajustar encaixa a imagem na janela. 100% usa a resolução original. Alterações só são gravadas ao salvar.{!canSave?" Gravação disponível para PNG e JPEG.":""}</p>
  </footer>
  {frames&&onFrame&&activeFrame>=0&&<nav className="viewer-filmstrip" aria-label="Miniaturas da sequência" inert={!!leaving||saving}>
    {frames.slice(Math.max(0,activeFrame-6), activeFrame+7).map(frame=>
      <FilmFrame key={frame.id} frame={frame} selected={frame.id===assetId}
        onClick={()=>{if(frame.id!==assetId)leave(()=>onFrame(frame.id));}} />)}
  </nav>}
 </dialog>;
}
