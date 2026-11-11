import {useRef, useState} from "react";
import type {Facet, FilterOption, FilterOptionsPage, PhotoFacets, PhotoFilters} from "./types";

const format = (value: string) => value.split("/").at(-1)?.toUpperCase() ?? value;

function FilterSelect({facet, label, value, options, more, open, onOpen, onChange}: {
  facet: Facet; label: string; value: string; options: FilterOption[];
  more?: boolean; open:boolean; onOpen:(open:boolean)=>void; onChange:(value:string)=>void;
}) {
  const select = useRef<HTMLSelectElement>(null);
  const [selected, setSelected] = useState<FilterOption>();
  const current = selected?.id === value && !options.some(option=>option.id===value) ? selected : null;
  const name = (option: FilterOption) => facet === "types" ? format(option.name) : option.name;
  const close = () => {onOpen(false);select.current?.focus();};
  return <>
    <select ref={select} aria-label={label} value={value} onChange={event=>{
      if (event.target.selectedOptions[0]?.dataset.more) onOpen(true);
      else {
        onOpen(false);
        setSelected(options.find(option=>option.id===event.target.value) ?? current ?? undefined);
        onChange(event.target.value);
      }
    }}>
      <option value="">{label}</option>
      {current&&<option value={current.id}>{name(current)}</option>}
      {options.map(option=><option key={option.id} value={option.id}>{name(option)}</option>)}
      {more&&window.photoManager?.listFilterOptions&&<option data-more="true">Mais opções…</option>}
    </select>
    {open&&<FilterOptionSearch facet={facet} label={label} options={options} renderName={name}
      onClose={close} onChoose={option=>{setSelected(option);close();onChange(option.id);}} />}
  </>;
}

function FilterOptionSearch({facet, label, options, renderName, onChoose, onClose}: {
  facet:Facet; label:string; options:FilterOption[]; renderName:(option:FilterOption)=>string;
  onChoose:(option:FilterOption)=>void; onClose:()=>void;
}) {
  const [draft, setDraft] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState<FilterOptionsPage>({options,next_offset:options.length});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function load(term: string, offset: number) {
    const list = window.photoManager?.listFilterOptions;
    if (!list || busy) return;
    setBusy(true);
    setError(false);
    try {
      const result = await list(facet, term, offset);
      setPage(previous=>offset ? {
        ...result,
        options:[...new Map([...previous.options,...result.options].map(option=>[option.id,option])).values()],
      } : result);
      setKeyword(term);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  const nextOffset = page.next_offset;
  return <section className="facet-options" aria-label={`Opções de ${label}`} onKeyDown={event=>{
    if (event.key === "Escape") {event.stopPropagation();onClose();}
  }}>
    <form onSubmit={event=>{event.preventDefault();void load(draft.trim(),0);}}>
      <input type="search" aria-label={`Buscar opções de ${label}`} placeholder={`Buscar em ${label.toLowerCase()}…`}
        maxLength={200} value={draft} onChange={event=>setDraft(event.target.value)} autoFocus />
      <button type="submit" disabled={busy}>Buscar opções</button>
      <button type="button" onClick={onClose}>Fechar</button>
    </form>
    <ul>
      {page.options.map(option=><li key={option.id}><button onClick={()=>onChoose(option)}>{renderName(option)}</button></li>)}
    </ul>
    {!page.options.length&&<p>Nenhuma opção encontrada.</p>}
    {error&&<p role="alert">Falha ao carregar opções. Tente novamente.</p>}
    {nextOffset!==null&&<button disabled={busy} onClick={()=>void load(keyword,nextOffset)}>Carregar mais opções</button>}
    {busy&&<p role="status">Carregando opções…</p>}
  </section>;
}

export function PhotoFilterBar({filters, facets, favorites, onFavorites, onChange, period, onClearPeriod}: {
  filters: PhotoFilters; facets?: PhotoFacets; favorites: boolean;
  onFavorites: (value:boolean)=>void; onChange:(value:PhotoFilters)=>void;
  period: string|null; onClearPeriod:()=>void;
}) {
  const [openFacet, setOpenFacet] = useState<Facet|null>(null);
  const keyword = filters.keyword ?? "";
  const [draft, setDraft] = useState(keyword);
  const [submittedKeyword, setSubmittedKeyword] = useState(keyword);
  if (keyword !== submittedKeyword) {
    setSubmittedKeyword(keyword);
    setDraft(keyword);
  }
  function update(key: keyof PhotoFilters, value: string | number) {
    const next = {...filters};
    if (value === "") delete next[key];
    else Object.assign(next, {[key]:value});
    onChange(next);
  }
  return <section className="gallery-filters" aria-label="Filtros da biblioteca">
    <FilterSelect facet="tags" label="Rótulos" value={filters.tag_id??""} options={facets?.tags??[]}
      more={facets?.more?.includes("tags")} open={openFacet==="tags"} onOpen={open=>setOpenFacet(open?"tags":null)} onChange={value=>update("tag_id",value)} />
    <select aria-label="Classificação" value={filters.rating??""} onChange={e=>update("rating",e.target.value?Number(e.target.value):"")}>
      <option value="">Classificação</option>
      {[1,2,3,4,5].map(n=><option key={n} value={n}>{"★".repeat(n)}</option>)}
    </select>
    {([{key:"media_type",facet:"types",label:"Tipo de imagem"},{key:"camera",facet:"cameras",label:"Câmera"},
      {key:"lens",facet:"lenses",label:"Lente"}] as const).map(({key,facet,label})=>
      <FilterSelect key={facet} facet={facet} label={label} value={filters[key]??""}
        options={(facets?.[facet]??[]).map(value=>({id:value,name:value}))}
        more={facets?.more?.includes(facet)} open={openFacet===facet} onOpen={open=>setOpenFacet(open?facet:null)} onChange={value=>update(key,value)} />
    )}
    <form role="search" onSubmit={e=>{e.preventDefault();update("keyword",draft.trim());}}>
      <input type="search" aria-label="Palavra-chave" placeholder="Buscar na biblioteca…" maxLength={200}
        value={draft} onChange={e=>setDraft(e.target.value)} />
      <button type="submit">Buscar</button>
    </form>
    <label><input type="checkbox" checked={favorites} onChange={e=>onFavorites(e.target.checked)} /> Favoritos</label>
    {Object.keys(filters).length>0&&<button onClick={()=>{setDraft("");onChange({});}}>Limpar filtros</button>}
    {period&&<><span>{period==="undated"?"Sem data de captura":`Captura: ${period}`}</span><button onClick={onClearPeriod}>Limpar período</button></>}
  </section>;
}
