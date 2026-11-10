import {useEffect,useRef,useState} from "react";
export function ImageViewer({assetId,onClose,restoreFocus}: {assetId:string;onClose:()=>void;restoreFocus?:()=>void}) {
  const [url,setUrl]=useState<string|null>(null);
  const [failed,setFailed]=useState(false);
  const [naturalWidth,setNaturalWidth]=useState(0);
  const [zoom,setZoom]=useState(0);
  const [attempt,setAttempt]=useState(0);
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;dialog.current?.showModal();return ()=>{if(restoreFocus)restoreFocus();else previous?.focus({preventScroll:true});};},[restoreFocus]);
  useEffect(()=>{
    let active=true;
    void (async()=>{
      const deadline=Date.now()+12000;
      try {
        while(active){
          const value=await window.photoManager?.getPreview?.(assetId) as {status?:string;media_type?:string;base64?:string}|null;
          if(!active)return;
          if(value?.status==="pending"&&Date.now()<deadline){await new Promise(resolve=>setTimeout(resolve,150));continue;}
          if(value?.media_type!=="image/jpeg"||typeof value.base64!=="string"||value.base64.length>220000||!/^\/9j\/[A-Za-z0-9+/]*={0,2}$/.test(value.base64)||value.base64.length%4!==0)throw new Error();
          setUrl(`data:image/jpeg;base64,${value.base64}`);setFailed(false);return;
        }
      }catch{if(active)setFailed(true);}
    })();return ()=>{active=false;};
  },[assetId,attempt]);
  return <dialog className="image-viewer" ref={dialog} aria-label="Visualizar imagem" onKeyDown={event=>{if(event.key==="Escape")event.stopPropagation();}} onCancel={event=>{event.preventDefault();onClose();}}>
    <header><strong>Visualizar imagem</strong><span>Prévia até 1280 × 960 · Original preservado</span><button onClick={()=>setZoom(0)}>Ajustar</button><button onClick={()=>setZoom(100)}>100%</button><button aria-label="Ampliar imagem" onClick={()=>setZoom(value=>Math.min(200,(value||100)+25))}>+</button><button aria-label="Reduzir imagem" onClick={()=>setZoom(value=>Math.max(25,(value||100)-25))}>−</button><button autoFocus onClick={onClose}>Fechar imagem</button></header>
    <div className={`viewer-image${zoom ? " viewer-zoomed" : ""}`}>
      {url ? <img src={url} alt="Prévia da imagem selecionada" onLoad={event=>setNaturalWidth(event.currentTarget.naturalWidth)} onError={()=>{setUrl(null);setFailed(true);}} style={zoom&&naturalWidth?{width:`${naturalWidth*zoom/100}px`,maxWidth:"none",maxHeight:"none"}:undefined}/> : failed ? <div role="alert"><p>Prévia indisponível. O arquivo pode estar offline, ter mudado ou não ser decodificável dentro dos limites.</p><button onClick={()=>{setFailed(false);setAttempt(n=>n+1);}}>Tentar prévia novamente</button></div> : <p role="status">Preparando prévia…</p>}
    </div>
  </dialog>;
}
