import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {FolderMonitor} from "./FolderMonitor";
import { FolderImportPanel } from "./FolderImportPanel";
import { FavoriteButton } from "./FavoriteButton";
import { CaptureCalendar } from "./CaptureCalendar";
import { ImageViewer } from "./ImageViewer";
import { DesktopMenu } from "./DesktopMenu";
import { AssetDetailsPanel } from "./AssetDetailsPanel";
import { DuplicatesView } from "./DuplicatesView";
import {mediaMenu} from "./media-menu";
import { MediaCard } from "./MediaCard";
import { LibraryWorkspace } from "./LibraryWorkspace";
import { CatalogingPanel } from "./CatalogingPanel";
import { useLibrarySession } from "./LibrarySession";
import { AvailabilityIndicator } from "./AvailabilityIndicator";
import type { AnnotationField, GalleryItem, GalleryPage } from "./types";

type State = { kind: "loading" } | { kind: "ready"; page: GalleryPage } | { kind: "error" };
async function requestGallery(retry = false, capturePeriod: string | null = null, favoritesOnly=false, rootId?: string): Promise<GalleryPage> {
  const bridge = window.photoManager;
  if (!bridge) throw new Error("Desktop bridge unavailable");
  if (retry) {const page=await bridge.retryGallery();if(!capturePeriod&&!favoritesOnly&&!rootId)return page;}
  return bridge.listGallery({pageSize:24,...(rootId?{rootId}:{}),...(capturePeriod?{capturePeriod}:{}),...(favoritesOnly?{favoritesOnly:true}:{})});
}

type IconName = "library" | "album" | "tools" | "settings" | "photo" | "shield";

export function App() {
  return window.photoManager?.getLibraryState ? <LibraryWorkspace><GalleryApp /></LibraryWorkspace> : <GalleryApp />;
}

function GalleryApp() {
  const session = useLibrarySession();
  const [actionError,setActionError]=useState(false);
  const [importSequence,setImportSequence]=useState(0);
  const [preparing, setPreparing] = useState(false);
  const [display, setDisplay] = useState<"thumbnails" | "details">("thumbnails");
  const [calendar,setCalendar] = useState(false);
  const [calendarPeriod,setCalendarPeriod] = useState<string|null>(null);
  const [captureFilter,setCaptureFilter] = useState<string|null>(null);
  const [mediaRevision,setMediaRevision]=useState(0);
  const [viewer,setViewer] = useState<string|null>(null);
  const [viewerItems,setViewerItems] = useState<GalleryItem[]>([]);
  const [query, setQuery] = useState("");
  const [favorites, setFavorites] = useState(false);
  const [folder, setFolder] = useState<string | null>(null);
  const [roots, setRoots] = useState<GalleryPage["roots"]>(undefined);
  const rootId = roots?.find(root => root.id === folder)?.id;
  const [thumbnailSize, setThumbnailSize] = useState(150);
  const [propertiesOpen, setPropertiesOpen] = useState(true);
  const [leftWidth, setLeftWidth] = useState(210);
  const [rightWidth, setRightWidth] = useState(300);
  const [view, setView] = useState<"gallery" | "duplicates">("gallery");
  const [galleryRevision, setGalleryRevision] = useState(0);
  const galleryEpoch = useRef(0);
  const [generation, setGeneration] = useState(0);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [detailsRevision,setDetailsRevision]=useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => window.photoManager?.onBackendReset?.(() => { setGeneration((n) => n + 1); if (view === "duplicates") setSelected(null); }), [view]);
  const origin = useRef<HTMLButtonElement | null>(null);
  const restoreViewerFocus=useCallback(()=>{const id=origin.current?.dataset.assetId;const target=origin.current?.isConnected?origin.current:[...document.querySelectorAll<HTMLButtonElement>("[data-asset-id]")].find(button=>button.dataset.assetId===id);target?.focus({preventScroll:true});},[]);
  const closeDetails = () => {
    const target = origin.current?.isConnected ? origin.current : [...document.querySelectorAll<HTMLButtonElement>("[data-asset-id]")].find((button) => button.dataset.assetId === selected);
    setSelected(null); target?.focus();
  };
  const changeDisplay = (next: "thumbnails" | "details") => { if (view !== "gallery") setSelected(null); setView("gallery"); setDisplay(next); setCalendar(false); };
  const [paging, setPaging] = useState(false);
  const [pageError, setPageError] = useState(false);
  const inFlight = useRef(false);
  const more = async () => {
    if (inFlight.current || state.kind !== "ready" || !state.page.next_cursor) return;
    const epoch = galleryEpoch.current;
    inFlight.current = true;
    setPaging(true);
    setPageError(false);
    try {
      const page = await window.photoManager!.listGallery({ pageSize: 24, after: state.page.next_cursor, ...(rootId ? {rootId} : {}), ...(captureFilter?{capturePeriod:captureFilter}:{}),...(favorites?{favoritesOnly:true}:{}) });
      if (epoch === galleryEpoch.current) setState({ kind: "ready", page: { ...page, items: [...state.page.items, ...page.items] } });
    } catch { if (epoch === galleryEpoch.current) setPageError(true); }
    finally { if (epoch === galleryEpoch.current) {inFlight.current = false; setPaging(false);} }
  };
  useEffect(()=>window.photoManager?.onGalleryChanged?.(()=>{
    galleryEpoch.current++;inFlight.current=false;setPaging(false);setPageError(false);setGalleryRevision(value=>value+1);
  }),[]);
  const load = () => {
    setSelected(null);
    setPageError(false);
    setState({ kind: "loading" });
    const epoch = galleryEpoch.current;
    void requestGallery(true, captureFilter, favorites, rootId)
      .then((page) => {
        if (epoch !== galleryEpoch.current) return;
        setState({kind: "ready", page});
        if (page.roots) setRoots(page.roots);
      })
      .catch(() => {if (epoch === galleryEpoch.current) setState({kind: "error"});});
  };
  useEffect(() => {
    let active = true;
    void requestGallery(false,captureFilter,favorites,rootId)
      .then((page) => {
        if (!active) return;
        setState({kind: "ready", page});
        if (page.roots) setRoots(page.roots);
      })
      .catch(() => { if (active) setState({ kind: "error" }); });
    return () => { active = false; };
  }, [galleryRevision,captureFilter,favorites,rootId]);

  const items = state.kind === "ready" ? state.page.items : [];
  // Text search applies to loaded items. Desktop folder pages arrive scoped by root ID.
  const folders = roots ?? [...new Set(items.map((item) => item.representative_location?.root_display_name).filter((name): name is string => !!name))].map(name => ({id:name,name}));
  const visible = items.filter((item) => (!favorites || item.annotation.favorite) && (!folder || rootId || item.representative_location?.root_display_name === folder) && `${item.annotation.title ?? ""} ${item.representative_location?.relative_path ?? ""}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const selectAsset = (id: string, button: HTMLButtonElement) => { origin.current = button; setSelected(id); setPropertiesOpen(true); };
  const showViewerAsset=(id:string)=>{
    const button=[...document.querySelectorAll<HTMLButtonElement>("[data-asset-id]")].find(candidate=>candidate.dataset.assetId===id);
    if(button)origin.current=button;
    setSelected(id);setPropertiesOpen(true);setViewer(id);
  };
  const openAsset=(id:string)=>{
    const sequence = visible.filter(item => item.kind === "photo");
    if (!sequence.some(item => item.asset_id === id)) return;
    setViewerItems(sequence);
    showViewerAsset(id);
  };
  const annotationChanged=(id:string, field:AnnotationField, value:string|number|null)=>{
    if (field !== "rating" && field !== "title") return;
    const edited = field === "rating" ? {rating:value as number|null} : {title:value as string|null};
    galleryEpoch.current++;
    inFlight.current=false;
    setPaging(false);
    setState(previous => previous.kind === "ready" ? {kind:"ready", page:{
      ...previous.page, items:previous.page.items.map(item => item.asset_id === id
        ? {...item, annotation:{...item.annotation, ...edited}} : item),
    }} : previous);
  };
  const viewerIndex=viewerItems.findIndex(item=>item.asset_id===viewer);
  const viewerName=viewerItems[viewerIndex]?.representative_location?.relative_path.split("/").pop()??"Imagem selecionada";
  const resetSelection = () => setSelected(null);
  const canEditFavorites=!!session && !!window.photoManager?.setFavorite;
  const changeFavorites=(value:boolean)=>{
    if(value===favorites)return;
    galleryEpoch.current++;inFlight.current=false;setPaging(false);setPageError(false);
    setSelected(null);setState({kind:"loading"});setFavorites(value);
  };
  const favoriteChanged=(id:string,value:boolean)=>{
    galleryEpoch.current++;inFlight.current=false;setPaging(false);
    setState(previous=>previous.kind!=="ready"?previous:{kind:"ready",page:{...previous.page,items:previous.page.items.map(item=>item.asset_id===id?{...item,annotation:{...item.annotation,favorite:value}}:item).filter(item=>!favorites||item.annotation.favorite)}});
    if(favorites&&value)setGalleryRevision(n=>n+1);
    setDetailsRevision(n=>n+1);
  };
  const openCalendar=(period:string|null)=>{setView("gallery");setPreparing(false);setPropertiesOpen(false);setCalendarPeriod(period);setCalendar(true);};
  const browsePeriod=(period:string|null)=>{
    galleryEpoch.current++; inFlight.current=false; setPaging(false);setPageError(false);setSelected(null);setState({kind:"loading"});
    setCalendar(false);setCaptureFilter(period);setGalleryRevision(n=>n+1);
  };
  return <div className={`app-shell${propertiesOpen ? " with-properties" : ""}`} style={{"--left-width": `${leftWidth}px`, "--right-width": `${rightWidth}px`, "--thumbnail-size": `${thumbnailSize}px`} as CSSProperties}>
      <nav className="workspace-menu" aria-label="Menus da área de trabalho">
        {session?.fileMenu ?? <DesktopMenu label="Arquivo"><button disabled>Bibliotecas indisponíveis no demo</button></DesktopMenu>}
        <DesktopMenu label="Editar"><button disabled={!selected} onClick={()=>setPropertiesOpen(true)}>Anotações da foto</button></DesktopMenu>
        <DesktopMenu label="Exibir">
          <button onClick={() => changeDisplay("thumbnails")}>Miniaturas</button>
          <button onClick={() => changeDisplay("details")}>Detalhes</button>
          <button disabled={!window.photoManager?.getCalendar} onClick={()=>openCalendar(null)}>Calendário por captura</button>
          <hr />
          <button onClick={() => setPropertiesOpen((open) => !open)}>Mostrar / ocultar propriedades</button>
        </DesktopMenu>
        <DesktopMenu label="Ferramentas">{session?.catalogingEnabled && <button onClick={()=>{setCalendar(false);setPreparing(true);}}>Preparação avançada</button>}<button onClick={() => {resetSelection(); setView("duplicates");}}>Duplicatas exatas</button></DesktopMenu>
        <DesktopMenu label="Ajuda"><p>Operação local. Imagens só são alteradas ao salvar. Favoritos, período e pastas consultam o catálogo. A busca por texto filtra os itens carregados.</p></DesktopMenu>
      </nav>
    <Sidebar view={view} folders={folders} folder={folder} favorites={favorites} canPrepare={!!session?.catalogingEnabled||!!session?.folderImportEnabled} preparing={preparing} onPrepare={() => {setCalendar(false);if(session?.folderImportEnabled){setPreparing(false);setImportSequence(value=>value+1);}else setPreparing(true);}} onSource={(sourceId, favorite) => {
      if (calendar || captureFilter) browsePeriod(null);
      if (sourceId !== folder && roots) {
        galleryEpoch.current++;
        inFlight.current = false;
        setPaging(false);
        setPageError(false);
        setState({kind: "loading"});
      }
      setFolder(sourceId);
      changeFavorites(favorite);
      setView("gallery");
      resetSelection();
    }} onNavigate={(next) => { setSelected(null); setView(next); }} />
    <PanelResize label="Largura da navegação" value={leftWidth} min={170} max={300} onChange={setLeftWidth} />
    <main className="workspace">
      <header className="view-toolbar">
        <h1>{view === "gallery" ? "Biblioteca" : "Duplicatas exatas"}</h1>
        <button aria-pressed={display === "thumbnails"} onClick={() => changeDisplay("thumbnails")}>Miniaturas</button>
        <button aria-pressed={display === "details"} onClick={() => changeDisplay("details")}>Detalhes</button>
        <span className="calendar-toolbar"><button disabled={!window.photoManager?.getCalendar} aria-pressed={calendar} onClick={()=>calendar?setCalendar(false):openCalendar(calendarPeriod)}>Calendário</button><button disabled={!window.photoManager?.getCalendar} onClick={()=>openCalendar(null)}>Ano</button><button disabled={!window.photoManager?.getCalendar} onClick={()=>openCalendar(calendarPeriod?.slice(0,4)??String(new Date().getFullYear()))}>Mês</button><button disabled={!window.photoManager?.getCalendar} onClick={()=>openCalendar(calendarPeriod?.length===7?calendarPeriod:`${calendarPeriod??new Date().getFullYear()}-${String(new Date().getMonth()+1).padStart(2,"0")}`)}>Dia</button></span>
        <label>Tamanho <input aria-label="Tamanho das miniaturas" type="range" min="110" max="240" value={thumbnailSize} onChange={(event) => setThumbnailSize(Number(event.target.value))} /></label>
        <button aria-pressed={propertiesOpen} onClick={() => setPropertiesOpen((open) => !open)}>Propriedades</button>
      </header>
      {session?.folderImportEnabled&&window.photoManager?.getIndexStatus&&<FolderMonitor/>}
      {actionError&&<p role="alert">Não foi possível executar a ação. Confira se a imagem e a biblioteca continuam disponíveis.</p>}
      {session?.folderImportEnabled && importSequence>0 && <FolderImportPanel key={importSequence} sessionId={session.sessionId} onApplied={()=>{
        galleryEpoch.current++;inFlight.current=false;setPaging(false);setPageError(false);setSelected(null);setQuery("");setFolder(null);setFavorites(false);setCaptureFilter(null);setCalendarPeriod(null);setCalendar(false);setView("gallery");setState({kind:"loading"});setGalleryRevision(value=>value+1);
      }} />}
      {session?.catalogingEnabled && <section className="preparation-workflow" hidden={!preparing} aria-label="Adicionar pastas">
        <button className="workflow-close" onClick={() => setPreparing(false)}>Recolher preparação</button>
        <CatalogingPanel sessionId={session.sessionId} onShowLibrary={() => setPreparing(false)} onApplied={() => {
          galleryEpoch.current++; inFlight.current = false; setPaging(false); setPageError(false);
          setSelected(null); setQuery(""); setCaptureFilter(null); setCalendar(false); setFolder(null); setFavorites(false); setView("gallery");
          setState({kind: "loading"}); setGalleryRevision((value) => value + 1);
        }} />
      </section>}
      {view === "gallery" && !calendar && <div className="gallery-filters">
        <label>Pesquisar nos itens carregados <input type="search" value={query} onChange={(event) => {setQuery(event.target.value); resetSelection();}} /></label>
        <label><input type="checkbox" checked={favorites} onChange={(event) => {changeFavorites(event.target.checked); resetSelection();}} /> Favoritos</label>
        <span>{captureFilter ? captureFilter === "undated" ? "Sem data de captura" : `Captura: ${captureFilter}` : folders.find(source => source.id === folder)?.name ?? "Todos os itens carregados"}</span>{captureFilter&&<button onClick={()=>browsePeriod(null)}>Limpar período</button>}
      </div>}
      {view === "gallery" && calendar && <CaptureCalendar key={galleryRevision} period={calendarPeriod} onPeriod={setCalendarPeriod} onBrowse={browsePeriod} />}
      <div hidden={view !== "gallery" || calendar} className="content" aria-busy={state.kind === "loading" || paging}>
        {state.kind === "loading" && <Status icon="photo" title="Abrindo o catálogo…" body="Conectando ao backend local seguro. Seus arquivos permanecem inalterados." />}
        {state.kind === "error" && <Status icon="photo" title="Não foi possível abrir a biblioteca" body="O backend local não respondeu. Nenhum arquivo foi alterado e você pode tentar novamente." action={<button className="primary-button" onClick={load}>Tentar novamente</button>} tone="error" />}
        {state.kind === "ready" && state.page.items.length === 0 && <Status icon="photo" title={favorites?"Nenhum favorito encontrado":captureFilter?"Nenhuma imagem neste período":"Sua biblioteca está vazia"} body={favorites?"Marque fotos como favoritas na biblioteca. Este filtro consulta todo o catálogo, respeitando o período selecionado.":"O catálogo local está aberto e pronto. Use Adicionar pastas para escolher um diretório e carregar suas imagens."} note="Nada foi importado ou alterado nos seus arquivos." />}
        {state.kind === "ready" && state.page.items.length > 0 && <section className="gallery" aria-labelledby="gallery-heading">
          <h2 id="gallery-heading" className="sr-only">Fotos e vídeos</h2>
          {!visible.length && <p role="status">Nenhum item carregado corresponde aos filtros. Carregue mais itens ou altere os filtros.</p>}
          {display === "thumbnails" ? <div className="media-grid" role="list">{visible.map((item) => <MediaCard key={`${item.asset_id}:${mediaRevision}`} item={item} selected={selected === item.asset_id} onFavoriteChanged={canEditFavorites?(value)=>favoriteChanged(item.asset_id,value):undefined} onOpen={window.photoManager?.getPreview ? ()=>openAsset(item.asset_id) : undefined} onSelect={(button) => selectAsset(item.asset_id, button)} />)}</div>
            : <div className="gallery-table"><table><thead><tr><th>Nome</th><th>Pasta</th><th>Formato</th><th>Disponibilidade</th><th>Favorito</th></tr></thead><tbody>{visible.map((item) => <tr key={item.asset_id} onContextMenu={event=>void mediaMenu(event,item.asset_id,button=>selectAsset(item.asset_id,button),()=>openAsset(item.asset_id),()=>setActionError(true))} onKeyDown={event=>{if(event.key==="ContextMenu"||(event.shiftKey&&event.key==="F10"))void mediaMenu(event,item.asset_id,button=>selectAsset(item.asset_id,button),()=>openAsset(item.asset_id),()=>setActionError(true));}}><td><button data-asset-id={item.asset_id} aria-pressed={selected === item.asset_id} onClick={(event) => selectAsset(item.asset_id, event.currentTarget)}>{item.annotation.title?.trim() || item.representative_location?.relative_path || "Sem título"}</button></td><td>{item.representative_location?.root_display_name ?? "Sem localização"}</td><td>{item.media_type ?? "Desconhecido"}</td><td><AvailabilityIndicator availability={item.availability} /></td><td>{canEditFavorites?<FavoriteButton assetId={item.asset_id} favorite={item.annotation.favorite} onChanged={(value)=>favoriteChanged(item.asset_id,value)}/>:item.annotation.favorite?"★":"—"}</td></tr>)}</tbody></table></div>}
          <div className="pagination">
            {pageError && <p role="alert">Não foi possível carregar mais itens. Tente novamente ou reabra a biblioteca.</p>}
            {state.page.has_more ? <button className="primary-button" disabled={paging} onClick={() => void more()}>{paging ? "Carregando…" : pageError ? "Tentar carregar novamente" : "Carregar mais"}</button> : <p role="status">Fim da biblioteca</p>}
            {pageError && <button className="primary-button" onClick={load}>Reabrir biblioteca</button>}
          </div>
        </section>}
      </div>
      {view === "duplicates" && <DuplicatesView key={generation} detailsOpen={selected !== null} onClearAsset={() => setSelected(null)} onAsset={selectAsset} />}
    </main>
    {propertiesOpen && <>
      <PanelResize label="Largura das propriedades" value={rightWidth} min={240} max={420} reverse onChange={setRightWidth} />
      {selected ? <AssetDetailsPanel suspended={viewer!==null} assetId={selected} onClose={closeDetails} revision={detailsRevision} onAnnotationChanged={session?(field,value)=>annotationChanged(selected,field,value):undefined} onFavoriteChanged={canEditFavorites?(value)=>favoriteChanged(selected,value):undefined} /> : <aside className="properties-empty"><h2>Propriedades</h2><p>Selecione uma foto ou vídeo para consultar seus dados.</p><p>Somente leitura</p></aside>}
    </>}
    {viewer && <ImageViewer assetId={viewer} canSave={["image/png","image/jpeg"].includes(viewerItems[viewerIndex]?.media_type??"")} name={viewerName} position={viewerIndex>=0?`${viewerIndex+1} de ${viewerItems.length} imagens carregadas`:undefined} onPrevious={viewerIndex>0?()=>showViewerAsset(viewerItems[viewerIndex-1].asset_id):undefined} onNext={viewerIndex>=0&&viewerIndex<viewerItems.length-1?()=>showViewerAsset(viewerItems[viewerIndex+1].asset_id):undefined} onSaved={()=>{setMediaRevision(value=>value+1);setDetailsRevision(value=>value+1);setGalleryRevision(value=>value+1);}} restoreFocus={restoreViewerFocus} onClose={()=>setViewer(null)} />}
    <footer className="workspace-status" role="status"><span>{view === "gallery" ? `${formatItemCount(items.length)} · ${visible.length} visíveis` : "Duplicatas exatas · Consulta somente leitura"} · {selected ? "1 selecionado" : "Nenhum selecionado"}</span><span>Operação local · Edições somente ao salvar</span></footer>
  </div>;
}

export function Sidebar({view = "gallery", onNavigate, folders = [], folder = null, favorites = false, canPrepare = false, preparing = false, onPrepare, onSource}: {view?: "gallery" | "duplicates"; onNavigate?: (view: "gallery" | "duplicates") => void; folders?: {id: string; name: string}[]; folder?: string | null; favorites?: boolean; canPrepare?: boolean; preparing?: boolean; onPrepare?: () => void; onSource?: (folder: string | null, favorites: boolean) => void}) {
  return <aside className="sidebar">
    <div className="brand"><span className="brand-mark" aria-hidden="true">PM</span><span className="brand-name">PlayMemories<span className="sr-only"> Photo Manager</span></span></div>
    <section className="source-section"><h2>Notificações</h2><p>{preparing ? "Consulte o andamento no painel central" : "Consulte tarefas em Adicionar pastas"}</p></section>
    <section className="source-section"><h2>Câmeras e mídias</h2><p>Detecção de dispositivos ainda indisponível.</p></section>
    <nav className="primary-nav" aria-label="Principal">
      <NavItem icon="library" label="Biblioteca" active={view === "gallery" && !folder && !favorites} onClick={() => {onNavigate?.("gallery"); onSource?.(null, false);}} />
      <button className="nav-item" aria-pressed={favorites} onClick={() => onSource?.(null, true)}>☆ Favoritos</button>
      <section className="source-section"><h2>Pastas do catálogo</h2>{folders.map(({id,name}) => <button key={id} className={`nav-item${folder === id ? " is-active" : ""}`} aria-pressed={folder === id} onClick={() => onSource?.(id, false)}>{name}</button>)}{!folders.length && <p>Nenhuma pasta cadastrada.</p>}</section>
      <p className="nav-label">Ferramentas</p><NavItem icon="album" label="Duplicatas exatas" active={view === "duplicates"} onClick={() => onNavigate?.("duplicates")} /><NavItem icon="album" label="Álbuns" disabled />
    </nav>
    <div className="sidebar-footer"><button className="nav-item" disabled={!canPrepare} onClick={onPrepare} title={canPrepare ? "Adicionar pasta à biblioteca" : "Disponível no laboratório de ingestão"}>+ Adicionar pastas</button><p className="privacy-note"><Icon name="shield" /><span><strong>Local e offline</strong><br />Imagens só são alteradas ao salvar.</span></p></div>
  </aside>;
}

function PanelResize({label, value, min, max, reverse = false, onChange}: {label: string; value: number; min: number; max: number; reverse?: boolean; onChange: (value: number) => void}) {
  return <input className="panel-resize" aria-label={label} type="range" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} onPointerDown={(event) => {
    if (event.button !== 0) return;
    event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.dataset.startX = String(event.clientX); event.currentTarget.dataset.startWidth = String(value);
  }} onPointerMove={(event) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    const delta = (event.clientX - Number(event.currentTarget.dataset.startX)) * (reverse ? -1 : 1);
    onChange(Math.min(max, Math.max(min, Number(event.currentTarget.dataset.startWidth) + delta)));
  }} onPointerUp={(event) => {if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);}} />;
}

function NavItem({ icon, label, active = false, disabled = false, onClick }: { onClick?: () => void; icon: IconName; label: string; active?: boolean; disabled?: boolean }) {
  return <button className={`nav-item${active ? " is-active" : ""}`} type="button" onClick={onClick} aria-current={active ? "page" : undefined} aria-label={disabled ? `${label} — em breve` : label} title={disabled ? `${label} — em breve` : label} disabled={disabled}>
    <Icon name={icon} /><span>{label}</span>{disabled && <span className="coming-soon" aria-hidden="true">Em breve</span>}
  </button>;
}

export function Status({ title, body, icon, note, action, tone = "neutral" }: { title: string; body: string; icon: IconName; note?: string; action?: ReactNode; tone?: "neutral" | "error" }) {
  return <section className={`status-panel status-panel-${tone}`} role={tone === "error" ? "alert" : "status"}>
    <div className="status-illustration" aria-hidden="true"><span className="status-orbit" /><span className="status-icon"><Icon name={icon} /></span></div>
    <h2>{title}</h2><p>{body}</p>{action && <div className="status-actions">{action}</div>}{note && <p className="status-note"><Icon name="shield" />{note}</p>}
  </section>;
}

export function formatItemCount(count: number): string { return count === 1 ? "1 item carregado" : `${count} itens carregados`; }

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    library: <><path d="M4 5.5h16v14H4z" /><path d="M8 5.5V3.8h8v1.7M4 10h16" /></>,
    album: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="m7 16 3.5-4 2.5 3 2-2 2 3M8.5 9h.01" /></>,
    tools: <path d="M14.5 6.5a4 4 0 0 0-5 5L4 17l3 3 5.5-5.5a4 4 0 0 0 5-5L15 12l-3-3z" />,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1A7 7 0 0 0 15 6l-.4-2.6h-4L10 6a7 7 0 0 0-1.6 1.1l-2.4-1-2 3.4L6 11a7 7 0 0 0 0 2l-2 1.5 2 3.4 2.4-1A7 7 0 0 0 10 18l.5 2.6h4L15 18a7 7 0 0 0 1.6-1.1l2.4 1 2-3.4-2-1.5a7 7 0 0 0 .1-1Z" /></>,
    photo: <><rect x="3.5" y="5" width="17" height="14" rx="2" /><circle cx="9" cy="10" r="1.5" /><path d="m5.5 17 4.2-4.4 3.2 3.1 2.3-2.4 3.3 3.7" /></>,
    shield: <><path d="M12 3.5 19 6v5c0 4.4-2.9 7.7-7 9.5C7.9 18.7 5 15.4 5 11V6z" /><path d="m9 12 2 2 4-4" /></>,
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
