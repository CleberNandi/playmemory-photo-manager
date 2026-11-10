import {useEffect, useState} from "react";
const months = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
type Summary = {period: string | null; buckets: [string,number][]; undated:number; partial:number};
export function CaptureCalendar({period, onPeriod, onBrowse}: {period:string | null; onPeriod:(period:string | null)=>void; onBrowse:(period:string)=>void}) {
  const [result,setResult] = useState<{key:string|null;value:Summary} | null>(null);
  const [error,setError] = useState(false);
  const [attempt,setAttempt] = useState(0);
  useEffect(()=>{
    let active=true;
    void window.photoManager!.getCalendar!(period).then(value=>{if(active){setResult({key:period,value});setError(false);}}).catch(()=>{if(active)setError(true);});
    return ()=>{active=false;};
  },[period,attempt]);
  const data=result?.key===period ? result.value : null;
  const counts = new Map(data?.buckets ?? []);
  const year = period ? Number(period.slice(0,4)) : 2000;
  const month = period?.length === 7 ? Number(period.slice(5,7)) : 0;
  const monthDate = new Date(0); monthDate.setUTCFullYear(year || 2000,month ? month-1 : 0,1);
  const firstWeekday=monthDate.getUTCDay();
  const last=new Date(monthDate); last.setUTCMonth(last.getUTCMonth()+1,0);
  const shift = (delta:number) => {
    if(month){const d=new Date(monthDate);d.setUTCMonth(d.getUTCMonth()+delta);const y=d.getUTCFullYear();if(y>0&&y<10000)onPeriod(`${String(y).padStart(4,"0")}-${String(d.getUTCMonth()+1).padStart(2,"0")}`);}
    else if(year+delta>0&&year+delta<10000)onPeriod(String(year+delta).padStart(4,"0"));
  };
  return <section className="capture-calendar" aria-label="Calendário de captura">
    <header className="calendar-heading"><div><h2>{!period ? "Anos de captura" : month ? `${months[month-1]} de ${year}` : `Capturas em ${year}`}</h2><p>Datas de captura do catálogo inteiro. A data de catalogação não é usada.</p></div>
      <div><button onClick={()=>onPeriod(null)}>Todos os anos</button>{!!month&&<button onClick={()=>onPeriod(period!.slice(0,4))}>Meses do ano</button>}{period&&<><button aria-label="Período anterior" onClick={()=>shift(-1)}>‹</button><button aria-label="Próximo período" onClick={()=>shift(1)}>›</button><button onClick={()=>onBrowse(period)}>Ver fotos do período</button></>}</div>
    </header>
    {error ? <div role="alert">Não foi possível consultar o calendário. <button onClick={()=>setAttempt(n=>n+1)}>Tentar calendário novamente</button></div> : !data ? <p role="status">Carregando datas…</p> : <>
      {!period && <div className="calendar-years">{data.buckets.map(([key,count])=><button key={key} onClick={()=>onPeriod(key)}><strong>{key}</strong><span>{count} foto(s)</span></button>)}{!data.buckets.length&&<p>Nenhuma data de captura disponível.</p>}</div>}
      {period && !month && <div className="calendar-months">{months.map((name,index)=>{const key=`${period}-${String(index+1).padStart(2,"0")}`;const count=counts.get(key)??0;return <button key={key} disabled={!count} onClick={()=>onPeriod(key)}><strong>{name}</strong><span>{count} foto(s)</span></button>;})}</div>}
      {!!month && <div className="calendar-days">{["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"].map(day=><strong key={day}>{day}</strong>)}{Array.from({length:firstWeekday},(_,i)=><span key={`blank-${i}`} />)}{Array.from({length:last.getUTCDate()},(_,i)=>{const day=i+1;const key=`${period}-${String(day).padStart(2,"0")}`;const count=counts.get(key)??0;return <button key={key} disabled={!count} aria-label={`${key}: ${count} foto(s)`} onClick={()=>onBrowse(key)}><strong>{day}</strong><span>{count ? `${count} foto(s)` : ""}</span></button>;})}</div>}
      {!!data.partial&&<p>{data.partial} foto(s) com data parcial, sem precisão para o próximo nível. Use “Ver fotos do período”.</p>}
      <button className="undated-button" onClick={()=>onBrowse("undated")}>Sem data de captura ({data.undated})</button>
    </>}
  </section>;
}
