import { CatalogingReview } from "./CatalogingReview";
import { useEffect, useRef, useState } from "react";

interface Job {
  session_id: string; operation_id: string; revision: number;
  state: "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  phase: string | null; observed_count: number; verified_count: number; excluded_count: number;
  total: null; proposal_id: string | null; terminal_reason: string | null;
}
interface Page {
  proposal_id: string; next_cursor: string | null;
  items: {candidate_id: string; relative_path: string; state: string; reason: string; profile: string; decoding: string; selectable?: boolean}[];
}
const terminal = (job: Job) => ["completed", "cancelled", "failed"].includes(job.state);
const labels: Record<string, string> = {
  queued: "Na fila", running: "Preparando", cancelling: "Cancelando — aguardando encerramento",
  cancelled: "Preparação cancelada", completed: "Proposta preparada", failed: "Preparação interrompida",
  snapshot: "Consultando catálogo", scanning: "Examinando pasta", verifying: "Verificando arquivos",
  planning: "Preparando proposta", cleanup: "Aguardando encerramento",
};
const errors: Record<string, string> = {
  invalid_request: "A seleção retornou um caminho inválido. Selecione novamente a pasta (invalid_request).",
  not_found: "A pasta selecionada não foi encontrada (not_found).",
  stale_grant: "A seleção expirou ou já foi usada. Selecione a pasta novamente.",
  stale_session: "A sessão mudou. Reabra a biblioteca.", busy: "Há uma operação em andamento. Aguarde o encerramento.",
  covered_subfolder: "Esta subpasta já pertence a uma pasta do catálogo. Atualize a pasta principal para localizar as imagens.",
  unsafe_location: "A pasta se sobrepõe ao catálogo, a uma raiz ou a um destino protegido.",
  root_changed: "A pasta mudou. Selecione-a novamente.", permission_denied: "Sem permissão para ler a pasta.",
  resource_limit: "O limite desta preparação foi atingido.", unavailable: "O backend está indisponível. Reabra a biblioteca antes de continuar.",
};
function errorText(error: unknown) {
  const message = typeof error === "object" && error !== null && "message" in error ? String(error.message) : String(error);
  const code = Object.keys(errors).find((key) => new RegExp(`\\b${key}\\b`).test(message));
  return code ? errors[code] : "Não foi possível concluir a operação. Selecione novamente a pasta; nenhum pedido será repetido automaticamente.";
}

export function CatalogingPanel({sessionId, onApplied, onShowLibrary}: {sessionId: string; onApplied?: () => void; onShowLibrary?: () => void}) {
  const [applicationBlocked, setApplicationBlocked] = useState(false);
  const [grant, setGrant] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const epoch = useRef(0);
  const lock = useRef(false);
  const latest = useRef<Job | null>(null);
  useEffect(() => {
    const invalidate = () => { epoch.current++; };
    return invalidate;
  }, [sessionId]);
  const accept = (value: Job) => {
    const previous = latest.current;
    if (value.session_id !== sessionId || (previous && (value.operation_id !== previous.operation_id || value.revision < previous.revision || terminal(previous)))) return;
    latest.current = value; setJob(value);
  };
  const active = job !== null && !terminal(job);
  useEffect(() => {
    if (!job || terminal(job)) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await window.photoManager!.getPreparationStatus!(sessionId, job.operation_id) as Job;
        if (!disposed) { accept(value); if (!latest.current || !terminal(latest.current)) timer = setTimeout(() => void poll(), 250); }
      } catch (failure) { if (!disposed) setError(errorText(failure)); }
    };
    timer = setTimeout(() => void poll(), 250);
    return () => { disposed = true; clearTimeout(timer); };
    // Operation identity owns this polling loop; revisions do not start concurrent requests.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, job?.operation_id]);
  const act = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true; setPending(true); setError(null);
    const current = epoch.current;
    try { await action(); } catch (failure) { if (current === epoch.current) setError(errorText(failure)); }
    finally { lock.current = false; if (current === epoch.current) setPending(false); }
  };
  const choose = () => act(async () => {
    const current = epoch.current;
    const result = await window.photoManager!.chooseMediaRoot!(sessionId) as {cancelled?: boolean; root_grant_id?: string};
    if (current !== epoch.current || result.cancelled) return;
    latest.current = null; setJob(null); setPage(null); setGrant(result.root_grant_id ?? null);
  });
  const prepare = () => act(async () => {
    if (!grant) return;
    const current = epoch.current;
    const selected = grant; setGrant(null); setPage(null); latest.current = null;
    const value = await window.photoManager!.prepareCataloging!(sessionId, selected, true) as Job;
    if (current === epoch.current) accept(value);
  });
  const cancel = () => act(async () => {
    if (!job) return;
    const current = epoch.current;
    const value = await window.photoManager!.cancelPreparation!(sessionId, job.operation_id) as {job: Job};
    if (current === epoch.current) accept(value.job);
  });
  const loadPage = () => act(async () => {
    if (job?.state !== "completed" || !job.proposal_id) return;
    const current = epoch.current;
    const value = await window.photoManager!.listCatalogingCandidates!(sessionId, job.proposal_id, page?.next_cursor ?? null, 50) as Page;
    if (current === epoch.current && value.proposal_id === job.proposal_id) setPage(value);
  });
  return <section className="cataloging-panel" aria-label="Preparar catalogação">
    <h2>Preparar catalogação</h2>
    <p>Examina a pasta e suas subpastas para preparar uma proposta. Os originais permanecem inalterados. Preparar não adiciona fotos; a catalogação exige revisão e confirmação separadas.</p>
    <button className="primary-button" disabled={pending || active || applicationBlocked} onClick={() => void choose()}>Selecionar pasta</button>{" "}
    <button className="primary-button" disabled={pending || active || applicationBlocked || !grant} onClick={() => void prepare()}>Preparar proposta</button>
    {grant && <p role="status">Pasta confirmada. Inicie em até cinco minutos; depois será necessário selecionar novamente.</p>}
    {job && <div role="status" aria-live="polite"><p>{labels[job.state]}{job.phase ? ` · ${labels[job.phase] ?? job.phase}` : ""}</p>
      <p>{job.observed_count} entradas observadas · {job.verified_count} verificadas · {job.excluded_count} excluídas. Total desconhecido.</p>
      {job.terminal_reason && <p>{errors[job.terminal_reason] ?? "A preparação não foi concluída."}</p>}
      {job.state === "completed" && <p>Verificação estrutural de imagens; a decodificação completa não foi verificada. A proposta pode estar vazia.</p>}
    </div>}
    {active && <button className="primary-button" disabled={pending || job.state === "cancelling"} onClick={() => void cancel()}>Cancelar preparação</button>}
    {error && <p role="alert">{error}</p>}
    {job?.state === "completed" && (!page || page.next_cursor) && <button className="primary-button" disabled={pending || applicationBlocked} onClick={() => void loadPage()}>{page ? "Próxima página" : "Ver proposta"}</button>}
    {page && <><p>Esta página contém {page.items.length} itens. {page.next_cursor ? "Há mais itens." : "Fim da proposta."}</p>
      {window.photoManager?.applyCataloging && job?.proposal_id
        ? <CatalogingReview key={job.proposal_id} sessionId={sessionId} proposalId={job.proposal_id} page={page} onLockChange={setApplicationBlocked} onApplied={onApplied} onShowLibrary={onShowLibrary} />
        : <div className="cataloging-table"><table><caption>Candidatos da proposta — sem aplicação</caption><thead><tr><th>Caminho relativo</th><th>Classificação</th><th>Motivo</th></tr></thead><tbody>{page.items.map((item) => <tr key={item.candidate_id}><td>{item.relative_path}</td><td>{item.state}</td><td>{item.reason}</td></tr>)}</tbody></table></div>}</>}
  </section>;
}
