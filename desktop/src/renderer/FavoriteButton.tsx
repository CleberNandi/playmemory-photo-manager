import {useEffect,useRef,useState} from "react";
export function FavoriteButton({assetId,favorite,onChanged}: {assetId:string;favorite:boolean;onChanged:(favorite:boolean)=>void}) {
  const [pending,setPending]=useState(false);
  const [failed,setFailed]=useState(false);
  const inFlight=useRef(false);
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return ()=>{mounted.current=false;};},[]);
  const save=async()=>{
    if(inFlight.current)return;
    inFlight.current=true;setPending(true);setFailed(false);
    try {
      const result=await window.photoManager!.setFavorite!(assetId,!favorite);
      if(!mounted.current)return;
      if(result.asset_id!==assetId||typeof result.favorite!=="boolean"||result.favorite!==!favorite)throw new Error();
      onChanged(result.favorite);
    } catch {if(mounted.current)setFailed(true);}
    finally {inFlight.current=false;if(mounted.current)setPending(false);}
  };
  return <span className="favorite-control"><button className="favorite-toggle" aria-pressed={favorite} aria-label={favorite?"Remover dos favoritos":"Adicionar aos favoritos"} disabled={pending} onClick={()=>void save()}>{pending?"Salvando…":favorite?"★ Favorito":"☆ Favoritar"}</button>{failed&&<span role="alert">Não foi possível confirmar o favorito. Reabra a biblioteca para conferir; nada será repetido automaticamente.</span>}</span>;
}
