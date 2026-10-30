import { useEffect, useRef, useState, type ReactNode } from "react";
import type { LibraryState } from "./types";

const messages: Record<string, string> = {
  not_found: "Catálogo não encontrado. Localize-o novamente ou escolha outro.",
  permission_denied: "Sem permissão de leitura e escrita para este catálogo.",
  corrupt: "O arquivo não é um catálogo íntegro.",
  incompatible: "Este catálogo não é compatível com esta versão do aplicativo.",
  upgrade_required: "Este catálogo requer uma atualização explícita, ainda indisponível.",
  busy: "Há uma operação em andamento ou o catálogo está indisponível. Tente novamente depois.",
  unsafe_location: "O destino não atende às verificações de segurança.",
  stale_session: "A sessão mudou. Escolha ou reabra a biblioteca.",
  internal_error: "Não foi possível concluir a operação. Você pode escolher outra biblioteca ou tentar reconectar.",
};

export function LibraryWorkspace({children}: {children: ReactNode}) {
  const [library, setLibrary] = useState<LibraryState | null>(null);
  const [operation, setOperation] = useState<string | null>(null);
  const mounted = useRef(false);
  const serial = useRef(0);
  const running = useRef(false);
  useEffect(() => {
    let active = true;
    mounted.current = true;
    const refresh = () => {
      const request = ++serial.current;
      void window.photoManager!.getLibraryState!().then((value) => {
        if (active && request === serial.current) setLibrary(value);
      }).catch(() => {
        if (active && request === serial.current) setLibrary({state: "unavailable", session: null, reopen: false, error: "internal_error"});
      });
    };
    refresh();
    const unsubscribe = window.photoManager?.onBackendReset?.(() => { setLibrary((previous) => previous?.state === "demo" ? previous : null); refresh(); });
    return () => { active = false; mounted.current = false; unsubscribe?.(); };
  }, []);
  const act = async (name: string, action: () => Promise<LibraryState>) => {
    if (running.current) return;
    running.current = true;
    const request = ++serial.current;
    setOperation(name);
    try {
      const value = await action();
      if (mounted.current && request === serial.current) setLibrary(value);
    } catch {
      if (mounted.current && request === serial.current) setLibrary((previous) => ({...(previous ?? {state: "unavailable", session: null, reopen: false}), error: "internal_error"}));
    } finally { running.current = false; if (mounted.current) setOperation(null); }
  };
  if (library?.state === "demo") return children;
  const api = window.photoManager!;
  return <div className="library-workspace">
    <section className="library-toolbar" aria-label="Gerenciar biblioteca" aria-busy={operation !== null}>
      <div className="library-identity"><strong>{library?.session?.display_name ?? "Nenhuma biblioteca ativa"}</strong>
        {library?.session && <small>Sessão {library.session.session_id.slice(0, 8)}</small>}</div>
      <div className="library-actions">
        <button className="primary-button" disabled={!!operation || !library} onClick={() => void act("Criando biblioteca…", () => api.chooseCreateLibrary!())}>Criar biblioteca</button>
        <button className="primary-button" disabled={!!operation || !library} onClick={() => void act("Abrindo biblioteca…", () => api.chooseOpenLibrary!())}>Abrir biblioteca</button>
        <button className="primary-button" disabled={!!operation || !library?.session} onClick={() => void act("Fechando biblioteca…", () => api.closeLibrary!(library!.session!.session_id))}>Fechar biblioteca</button>
        <button className="primary-button" disabled={!!operation || !library} onClick={() => void act("Esquecendo seleção…", () => api.forgetLibrary!())}>Esquecer última biblioteca</button>
      </div>
      <label><input type="checkbox" checked={library?.reopen ?? false} disabled={!!operation || !library} onChange={(event) => { const checked = event.target.checked; void act("Salvando preferência…", () => api.setReopenLibrary!(checked)); }} /> Reabrir ao iniciar</label>
      {operation && <p role="status">{operation}</p>}
      {library?.warning && <p role="alert">{library.warning === "preference_invalid" ? "A preferência anterior não pôde ser lida. Escolha uma biblioteca." : "A biblioteca continua aberta, mas a preferência não foi salva."}</p>}
      {library?.error && <p role="alert">{messages[library.error] ?? messages.internal_error}</p>}
    </section>
    {library?.state === "active" && library.session
      ? <div key={library.session.session_id}>{children}</div>
      : <section className="library-welcome" role="status"><h1>{library ? "Escolha uma biblioteca" : "Conectando ao backend local…"}</h1><p>Crie ou abra um catálogo fora das pastas de fotografias. Nenhuma mídia será examinada nesta etapa.</p>
        {library?.state === "unavailable" && <button className="primary-button" disabled={!!operation} onClick={() => void act("Reconectando…", async () => { try { await api.retryGallery(); } catch { /* A restart without an active library has no gallery. */ } return api.getLibraryState!(); })}>Reconectar backend</button>}
      </section>}
  </div>;
}
