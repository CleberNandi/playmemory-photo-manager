import {useEffect,useRef,useState} from "react";
export function viewerGeometry(width:number,height:number,rotation:number,zoom:number,viewportWidth:number,viewportHeight:number){
 const sideways=rotation%180!==0;
 const rotatedWidth=sideways?height:width,rotatedHeight=sideways?width:height;
 const scale=zoom?zoom/100:Math.min(1,Math.max(1,viewportWidth-24)/Math.max(1,rotatedWidth),Math.max(1,viewportHeight-24)/Math.max(1,rotatedHeight));
 return {width:width*scale,height:height*scale,boxWidth:rotatedWidth*scale,boxHeight:rotatedHeight*scale};
}
export function ImageViewer({assetId,onClose,restoreFocus,initialRotation=0,name="Imagem selecionada",position,onPrevious,onNext}: {assetId:string;onClose:()=>void;restoreFocus?:()=>void;initialRotation?:number;name?:string;position?:string;onPrevious?:()=>void;onNext?:()=>void}) {
 const [image,setImage]=useState<{id:string;url:string}|null>(null);
 const [failure,setFailure]=useState<string|null>(null);
 const [dimensions,setDimensions]=useState<{id:string;width:number;height:number}|null>(null);
 const [view,setView]=useState({id:assetId,zoom:0,rotation:initialRotation});
 const [retry,setRetry]=useState({id:assetId,value:0});
 const [viewport,setViewport]=useState({width:1280,height:960});
 const closeButton=useRef<HTMLButtonElement>(null);
 const dialog=useRef<HTMLDialogElement>(null),canvas=useRef<HTMLDivElement>(null);
 const rotation=view.id===assetId?view.rotation:initialRotation,zoom=view.id===assetId?view.zoom:0;
 const attempt=retry.id===assetId?retry.value:0;
 const url=image?.id===assetId?image.url:null;
 const size=dimensions?.id===assetId?dimensions:null;
 const failed=failure===assetId;
 if(view.id!==assetId)setView({id:assetId,zoom:0,rotation:initialRotation});
 const update=(next:{zoom?:number;rotation?:number})=>setView({id:assetId,zoom,rotation,...next});
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
   if(!dialog.current?.open||event.altKey||event.ctrlKey||event.metaKey)return;
   if(event.key!=="ArrowLeft"&&event.key!=="ArrowRight")return;
   event.preventDefault();event.stopPropagation();if(event.key==="ArrowLeft")onPrevious?.();else onNext?.();
  };
  document.addEventListener("keydown",keyboard);return ()=>document.removeEventListener("keydown",keyboard);
 },[onPrevious,onNext]);
 const geometry=size?viewerGeometry(size.width,size.height,rotation,zoom,viewport.width,viewport.height):null;
 return <dialog className="image-viewer" ref={dialog} aria-label="Visualizar imagem" onKeyDown={event=>{
  if(event.key==="Escape"){event.stopPropagation();return;}

 }} onCancel={event=>{event.preventDefault();onClose();}}>
  <header><strong>Visualizar imagem</strong><span>Prévia até 1280 × 960 · Original preservado · Rotação temporária</span>
   <button aria-label="Imagem anterior" disabled={!onPrevious} onClick={onPrevious}>Anterior</button><button aria-label="Próxima imagem" disabled={!onNext} onClick={onNext}>Próxima</button>
   <button onClick={()=>update({zoom:0})}>Ajustar</button><button onClick={()=>update({zoom:100})}>100%</button><button aria-label="Ampliar imagem" onClick={()=>update({zoom:Math.min(200,(zoom||100)+25)})}>+</button><button aria-label="Reduzir imagem" onClick={()=>update({zoom:Math.max(25,(zoom||100)-25)})}>−</button>
   <button disabled={!url} onClick={()=>rotate(-90)}>Girar à esquerda</button><button disabled={!url} onClick={()=>rotate(90)}>Girar à direita</button><button disabled={rotation===0} onClick={()=>update({rotation:0})}>Restaurar rotação</button><button ref={closeButton} autoFocus onClick={onClose}>Fechar imagem</button>
  </header>
  <p className="viewer-caption" role="status">{name}{position?` · ${position}`:""} · {rotation}°</p>
  <div ref={canvas} className={`viewer-image${zoom?" viewer-zoomed":""}`}>
   {url?<div className="viewer-stage" style={geometry?{width:geometry.boxWidth,height:geometry.boxHeight}:undefined}><img key={assetId} src={url} alt={`Prévia de ${name}`} onLoad={event=>setDimensions({id:assetId,width:event.currentTarget.naturalWidth,height:event.currentTarget.naturalHeight||1})} onError={()=>{setImage(null);setFailure(assetId);}} style={geometry?{width:`${geometry.width}px`,height:`${geometry.height}px`,maxWidth:"none",maxHeight:"none",transform:`translate(-50%, -50%) rotate(${rotation}deg)`}:{transform:`rotate(${rotation}deg)`}}/></div>:failed?<div role="alert"><p>Prévia indisponível. O arquivo pode estar offline, ter mudado ou não ser decodificável dentro dos limites.</p><button onClick={()=>{setFailure(null);setRetry({id:assetId,value:attempt+1});}}>Tentar prévia novamente</button></div>:<p role="status">Preparando prévia…</p>}
  </div>
 </dialog>;
}
