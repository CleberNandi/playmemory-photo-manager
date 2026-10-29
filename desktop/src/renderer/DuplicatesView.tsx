import { useEffect, useRef, useState } from "react";
import type { DuplicateGroup, DuplicateGroupPage, DuplicateListPage, DuplicateResult } from "./types";

type Failure = Exclude<DuplicateResult<DuplicateListPage>, {status: "ready"}>;
const errorText: Record<Failure["status"], string> = {
  analysis_not_available: "A análise de duplicatas ainda não está disponível nesta biblioteca. Nenhuma mídia foi analisada.",
  temporarily_unavailable: "O backend está temporariamente indisponível.",
  internal_error: "Não foi possível interpretar os dados de duplicatas.",
  invalid_request: "A solicitação de duplicatas não é válida.",
  stale_snapshot: "A sessão de demonstração mudou. Reabra a lista para não misturar evidências.",
  not_found: "Grupo não encontrado nesta sessão.",
  response_too_large: "A resposta excedeu o limite seguro. Nenhum dado foi truncado.",
};
export function DuplicateFailure({value, retry, reopen}: {value: Failure; retry: () => void; reopen?: () => void}) {
  const capability = value.status === "analysis_not_available";
  return <div role={capability ? "status" : "alert"} className="duplicate-notice"><p>{errorText[value.status]}</p>
    {!capability && (value.status === "stale_snapshot" ? <button className="primary-button" onClick={reopen ?? retry}>Reabrir lista</button> : <button className="primary-button" onClick={retry}>Tentar leitura novamente</button>)}
  </div>;
}
const blockNames: Record<string, string> = {hardlink: "Hardlink: nomes compartilham uma cópia física", identity_conflict: "Conflito de identidade", protected: "Dependências protegidas", incomplete_coverage: "Cobertura incompleta", preserved_copy_unverified: "Cópia preservada não verificada"};
function Blocks({values}: {values: string[]}) { return <ul className="duplicate-blocks">{values.map((b) => <li key={b}>{blockNames[b] ?? b}</li>)}</ul>; }
function Summary({group: g}: {group: DuplicateGroup}) {
  return <><p>{g.occurrence_count} ocorrências · {g.physical_copy_count} cópias físicas independentes (simuladas)</p>
    <p className="duplicate-digest">SHA-256 simulado: {g.sha256}</p><p>Tamanho simulado: {g.byte_size} bytes</p>
    <Blocks values={g.blocks} />
    {g.review ? <div className="duplicate-notice"><p>Revisão histórica {g.review.status === "stale" ? "desatualizada" : "registrada"}; sem revalidação.</p><p>{g.review.reason}</p></div> : <p>Revisão desconhecida · Estado do plano não conhecido</p>}
  </>;
}
export function Coverage({page}: {page: DuplicateListPage | DuplicateGroupPage}) {
  return <div className="duplicate-notice" role="status">
    <strong>{page.coverage === "complete" ? "Cobertura completa do cenário sintético" : page.coverage === "partial" ? "Cobertura parcial: não permite concluir ausência de duplicatas" : "Cobertura indisponível"}</strong>
    <p>{page.eligible_location_count} ocorrências elegíveis simuladas · {page.hashed_location_count} arquivos com hashing executado. Sem observação física.</p>
    {page.issues.length > 0 && <details><summary>{page.issues.length} impedimento(s) no cenário</summary><ul>{page.issues.map((issue, i) => <li key={i}>{issue.kind === "root_offline" ? "Raiz offline" : issue.kind} · {issue.relative_path}</li>)}</ul></details>}
  </div>;
}
export function DuplicatesView({onAsset, detailsOpen, onClearAsset}: {onAsset: (id: string, button: HTMLButtonElement) => void; detailsOpen: boolean; onClearAsset: () => void}) {
  const [page, setPage] = useState<DuplicateListPage | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [paging, setPaging] = useState(false);
  const [selection, setSelection] = useState<DuplicateGroup | null>(null);
  const alive = useRef(false);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const origin = useRef<HTMLButtonElement | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    generation.current++;
    alive.current = true;
    let active = true;
    void (async () => {
      try {
        const result = await window.photoManager?.listDuplicates?.({pageSize: 2});
        if (!active) return;
        if (result?.status === "ready") setPage(result.page);
        else setFailure(result ?? {status: "temporarily_unavailable"});
      } catch { if (active) setFailure({status: "temporarily_unavailable"}); }
    })();
    return () => { active = false; alive.current = false; };
  }, [attempt]);
  const reopen = () => { onClearAsset(); setSelection(null); setPage(null); setFailure(null); setAttempt((a) => a + 1); };
  const more = async () => {
    if (inFlight.current || !page?.next_cursor) return;
    const epoch = generation.current;
    inFlight.current = true; setPaging(true); setFailure(null);
    try {
      const result = await window.photoManager?.listDuplicates?.({pageSize: 2, after: page.next_cursor});
      if (!alive.current || epoch !== generation.current) return;
      if (result?.status === "ready" && result.page.snapshot_id === page.snapshot_id) setPage({...result.page, groups: [...page.groups, ...result.page.groups]});
      else setFailure(result?.status === "ready" ? {status: "stale_snapshot"} : result ?? {status: "temporarily_unavailable"});
    } catch { if (alive.current && epoch === generation.current) setFailure({status: "temporarily_unavailable"}); }
    finally { inFlight.current = false; if (alive.current && epoch === generation.current) setPaging(false); }
  };
  const close = () => { onClearAsset(); setSelection(null); origin.current?.focus(); };
  return <section className="duplicates-view" aria-labelledby="duplicates-heading">
    <h2 ref={heading} tabIndex={-1} id="duplicates-heading">Grupos de duplicatas exatas</h2>
    {page && <p className="synthetic-banner">Demonstração · Dados sintéticos. Hashes, cópias e revisões simulados. Nenhuma análise física executada.</p>}
    {failure && <DuplicateFailure value={failure} retry={page ? () => void more() : reopen} reopen={reopen} />}
    {!page && !failure && <p role="status">Carregando grupos…</p>}
    {page && <><Coverage page={page} />
      {!page.groups.length && <p role="status">{page.coverage === "complete" ? "Nenhum grupo no escopo sintético analisado." : "Nenhum grupo disponível; a cobertura não permite concluir ausência de duplicatas."}</p>}
      <div className="duplicate-layout"><div className="duplicate-list" aria-busy={paging}>
        <p>{page.groups.length} de {page.total_count} grupos carregados</p>
        {page.groups.map((g, i) => <article className="duplicate-card" key={g.group_key}>
          <h3><button className="group-select" aria-pressed={selection?.group_key === g.group_key} onClick={(event) => { onClearAsset(); origin.current = event.currentTarget; setSelection(g); }}>Grupo {i + 1}</button></h3><Summary group={g} />
        </article>)}
        <div className="pagination">{page.next_cursor ? <button className="primary-button more-groups" disabled={paging} onClick={() => void more()}>{paging ? "Carregando grupos…" : "Carregar mais grupos"}</button> : <p role="status">Fim dos grupos</p>}</div>
      </div>
      {selection && <GroupPanel key={selection.group_key} snapshotId={page.snapshot_id} group={selection} onClose={close} onAsset={onAsset} detailsOpen={detailsOpen} reopen={reopen} />}
      </div></>}
  </section>;
}
function GroupPanel({snapshotId, group, onClose, onAsset, detailsOpen, reopen}: {snapshotId: string; group: DuplicateGroup; onClose: () => void; onAsset: (id: string, button: HTMLButtonElement) => void; detailsOpen: boolean; reopen: () => void}) {
  const [page, setPage] = useState<DuplicateGroupPage | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [paging, setPaging] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const alive = useRef(false);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => { close.current?.focus(); }, []);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape" && !detailsOpen) onClose(); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose, detailsOpen]);
  useEffect(() => {
    generation.current++;
    alive.current = true; let active = true;
    void (async () => {
      try {
        const result = await window.photoManager?.getDuplicateGroup?.({snapshotId, groupKey: group.group_key, pageSize: 24});
        if (!active) return;
        if (result?.status === "ready" && result.page.snapshot_id === snapshotId && result.page.group.group_key === group.group_key) setPage(result.page);
        else setFailure(result?.status === "ready" ? {status: "stale_snapshot"} : result ?? {status: "temporarily_unavailable"});
      } catch { if (active) setFailure({status: "temporarily_unavailable"}); }
    })();
    return () => { active = false; alive.current = false; };
  }, [snapshotId, group.group_key, attempt]);
  const more = async () => {
    if (inFlight.current || !page?.next_cursor) return;
    const epoch = generation.current;
    inFlight.current = true; setPaging(true); setFailure(null);
    try {
      const result = await window.photoManager?.getDuplicateGroup?.({snapshotId, groupKey: group.group_key, pageSize: 24, after: page.next_cursor});
      if (!alive.current || epoch !== generation.current) return;
      if (result?.status === "ready" && result.page.snapshot_id === snapshotId && result.page.group.group_key === group.group_key) setPage({...result.page, members: [...page.members, ...result.page.members]});
      else setFailure(result?.status === "ready" ? {status: "stale_snapshot"} : result ?? {status: "temporarily_unavailable"});
    } catch { if (alive.current && epoch === generation.current) setFailure({status: "temporarily_unavailable"}); }
    finally { inFlight.current = false; if (alive.current && epoch === generation.current) setPaging(false); }
  };
  return <section className="duplicate-group" aria-labelledby="group-heading" aria-busy={!page && !failure || paging}>
    <header><h3 id="group-heading">Membros do grupo</h3><button ref={close} className="primary-button close-group" onClick={onClose}>Fechar grupo</button></header>
    <Summary group={group} />
    {!page && !failure && <p role="status">Carregando membros…</p>}
    {failure && <DuplicateFailure value={failure} retry={page ? () => void more() : () => {setFailure(null); setAttempt((a) => a + 1);}} reopen={reopen} />}
    {page && <><p role="status">{page.members.length} de {page.total_count} membros carregados</p><ul className="duplicate-members">{page.members.map((m) => <li key={m.location_id}>
      <p><strong>{m.root_display_name}</strong></p><p>{m.relative_path}</p>
      <p>{m.location_source === "projection_fixture" ? "Ocorrência simulada somente nesta projeção; não consta nas localizações do catálogo." : "Localização da fixture do catálogo; evidência de duplicação simulada."}</p>
      <p>Asset: {m.asset_id}</p><p>Localização: {m.location_id}</p>
      <p>{m.hardlinked ? "Hardlink simulado" : "Sem hardlink no cenário"} · {m.identity_conflict ? "Conflito de identidade" : "Sem conflito no cenário"}</p>
      <p>Proteção: {m.protected === null ? "desconhecida" : m.protected ? "protegido no cenário" : "não protegido no cenário"}</p><Blocks values={m.blocks} />
      <button className="primary-button member-details" onClick={(event) => onAsset(m.asset_id, event.currentTarget)}>Detalhes do Asset</button>
    </li>)}</ul>
    <div className="pagination">{page.next_cursor ? <button className="primary-button more-members" disabled={paging} onClick={() => void more()}>{paging ? "Carregando membros…" : "Carregar mais membros"}</button> : <p>Todos os membros carregados</p>}</div></>}
  </section>;
}
