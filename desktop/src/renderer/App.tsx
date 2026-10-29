import { useEffect, useRef, useState, type ReactNode } from "react";
import { MediaCard } from "./MediaCard";
import type { GalleryPage } from "./types";

type State = { kind: "loading" } | { kind: "ready"; page: GalleryPage } | { kind: "error" };
async function requestGallery(retry = false): Promise<GalleryPage> {
  const bridge = window.photoManager;
  if (!bridge) throw new Error("Desktop bridge unavailable");
  return retry ? bridge.retryGallery() : bridge.listGallery({ pageSize: 24 });
}

type IconName = "library" | "album" | "tools" | "settings" | "photo" | "shield";

export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [paging, setPaging] = useState(false);
  const [pageError, setPageError] = useState(false);
  const inFlight = useRef(false);
  const more = async () => {
    if (inFlight.current || state.kind !== "ready" || !state.page.next_cursor) return;
    inFlight.current = true;
    setPaging(true);
    setPageError(false);
    try {
      const page = await window.photoManager!.listGallery({ pageSize: 24, after: state.page.next_cursor });
      setState({ kind: "ready", page: { ...page, items: [...state.page.items, ...page.items] } });
    } catch { setPageError(true); }
    finally { inFlight.current = false; setPaging(false); }
  };
  const load = () => {
    setPageError(false);
    setState({ kind: "loading" });
    void requestGallery(true).then((page) => setState({ kind: "ready", page })).catch(() => setState({ kind: "error" }));
  };
  useEffect(() => {
    let active = true;
    void requestGallery()
      .then((page) => { if (active) setState({ kind: "ready", page }); })
      .catch(() => { if (active) setState({ kind: "error" }); });
    return () => { active = false; };
  }, []);

  return <div className="app-shell">
    <Sidebar />
    <main className="workspace">
      <header className="page-header">
        <div><p className="eyebrow">Sua coleção</p><h1>Biblioteca</h1></div>
        <div className="local-status"><Icon name="shield" /><span>Operação local</span></div>
      </header>
      <div className="content" aria-busy={state.kind === "loading" || paging}>
        {state.kind === "loading" && <Status icon="photo" title="Abrindo o catálogo…" body="Conectando ao backend local seguro. Seus arquivos permanecem inalterados." />}
        {state.kind === "error" && <Status icon="photo" title="Não foi possível abrir a biblioteca" body="O backend local não respondeu. Nenhum arquivo foi alterado e você pode tentar novamente." action={<button className="primary-button" onClick={load}>Tentar novamente</button>} tone="error" />}
        {state.kind === "ready" && state.page.items.length === 0 && <Status icon="photo" title="Sua biblioteca está vazia" body="O catálogo local está aberto e pronto. Adicionar pastas e catalogar fotos estará disponível em uma próxima etapa." note="Nada foi importado ou alterado nos seus arquivos." />}
        {state.kind === "ready" && state.page.items.length > 0 && <section className="gallery" aria-labelledby="gallery-heading">
          <div className="section-heading"><div><p className="section-kicker">Todos os itens</p><h2 id="gallery-heading">Fotos e vídeos</h2></div><p className="result-count">{formatItemCount(state.page.items.length)}</p></div>
          <div className="media-grid" role="list">{state.page.items.map((item) => <MediaCard key={item.asset_id} item={item} />)}</div>
          <div className="pagination">
            {pageError && <p role="alert">Não foi possível carregar mais itens. Tente novamente ou reabra a biblioteca.</p>}
            {state.page.has_more ? <button className="primary-button" disabled={paging} onClick={() => void more()}>{paging ? "Carregando…" : pageError ? "Tentar carregar novamente" : "Carregar mais"}</button> : <p role="status">Fim da biblioteca</p>}
            {pageError && <button className="primary-button" onClick={load}>Reabrir biblioteca</button>}
          </div>
        </section>}
      </div>
    </main>
  </div>;
}

export function Sidebar() {
  return <aside className="sidebar">
    <div className="brand"><span className="brand-mark" aria-hidden="true">PM</span><span className="brand-name">PlayMemories<span className="sr-only"> Photo Manager</span></span></div>
    <nav className="primary-nav" aria-label="Principal">
      <p className="nav-label">Coleção</p><NavItem icon="library" label="Biblioteca" active /><NavItem icon="album" label="Álbuns" disabled />
      <p className="nav-label nav-label-tools">Ferramentas</p><NavItem icon="tools" label="Ferramentas" disabled />
    </nav>
    <div className="sidebar-footer"><NavItem icon="settings" label="Configurações" disabled /><p className="privacy-note"><Icon name="shield" /><span><strong>Local e offline</strong><br />Seus originais não são alterados.</span></p></div>
  </aside>;
}

function NavItem({ icon, label, active = false, disabled = false }: { icon: IconName; label: string; active?: boolean; disabled?: boolean }) {
  return <button className={`nav-item${active ? " is-active" : ""}`} type="button" aria-current={active ? "page" : undefined} aria-label={disabled ? `${label} — em breve` : label} title={disabled ? `${label} — em breve` : label} disabled={disabled}>
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
