import { useEffect, useRef, useState } from "react";

export interface CandidatePage {
  proposal_id: string; next_cursor: string | null;
  items: {candidate_id: string; relative_path: string; state: string; reason: string; profile: string; decoding: string; selectable?: boolean}[];
}
interface Command {
  command_id: string; state: "queued" | "running" | "completed" | "outcome_unknown";
  result: {status: string; diagnostic: string | null; items: {candidate_id: string; disposition: string; asset_id: string | null; location_id: string | null}[]} | null;
}
const done = (command: Command) => command.state === "completed" || command.state === "outcome_unknown";
const reasonLabels: Record<string, string> = {eligible_jpeg: "JPEG estruturalmente aceito", unsupported_extension: "Formato ainda não suportado", not_regular_file: "Diretório, link ou entrada especial", invalid_jpeg_signature: "Assinatura JPEG inválida", truncated_jpeg: "JPEG incompleto", empty_file: "Arquivo vazio", byte_limit_exceeded: "Arquivo acima do limite de verificação", malformed_jpeg_segment: "Estrutura JPEG inválida", unsupported_jpeg_frame: "Tipo de JPEG ainda não suportado", dimension_limit_exceeded: "Dimensões acima do limite", segment_limit_exceeded: "Estrutura JPEG excede o limite"};

export function CatalogingReview({sessionId, proposalId, page, onLockChange, onApplied, onShowLibrary}: {sessionId: string; proposalId: string; page: CandidatePage; onLockChange: (value: boolean) => void; onApplied?: () => void; onShowLibrary?: () => void}) {
  const [selection, setSelection] = useState<Record<string, string>>({});
  const [command, setCommand] = useState<Command | null>(null);
  const [pending, setPending] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const mounted = useRef(true);
  const notified = useRef<string | null>(null);
  const inFlight = useRef(false);
  const callback = useRef(onApplied);
  useEffect(() => {callback.current = onApplied;}, [onApplied]);
  const count = Object.keys(selection).length;
  const locked = pending || uncertain || (command !== null && !done(command));
  useEffect(() => { onLockChange(locked); }, [locked, onLockChange]);
  useEffect(() => { mounted.current = true; return () => {mounted.current = false;}; }, []);
  const accept = (value: Command) => {
    if (!mounted.current) return;
    setCommand(value);
    if (value.state === "outcome_unknown") setUncertain(true);
    if (value.state === "completed" && value.result?.status === "applied" && notified.current !== value.command_id) {
      notified.current = value.command_id; callback.current?.();
    }
  };
  useEffect(() => {
    if (!command || done(command) || uncertain) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await window.photoManager!.getCatalogingApplicationStatus!(sessionId, command.command_id) as Command;
        if (!disposed && value.command_id === command.command_id && ["queued", "running", "completed", "outcome_unknown"].includes(value.state)) {
          accept(value);
          if (!done(value)) timer = setTimeout(() => void poll(), 250);
        } else if (!disposed) setUncertain(true);
      } catch {if (!disposed) setUncertain(true);}
    };
    timer = setTimeout(() => void poll(), 250);
    return () => {disposed = true; clearTimeout(timer);};
    // One nonoverlapping polling loop owns this command, independent of status renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, command?.command_id, uncertain]);
  const apply = async () => {
    if (!count || submitted || inFlight.current) return;
    inFlight.current = true; setPending(true); setSubmitted(true);
    const ids = Object.keys(selection);
    try {
      const value = await window.photoManager!.applyCataloging!(sessionId, proposalId, ids) as Command & {cancelled?: boolean};
      if (!mounted.current) return;
      if (value.cancelled) setSubmitted(false);
      else if (typeof value.command_id === "string" && ["queued", "running", "completed", "outcome_unknown"].includes(value.state)) accept(value);
      else setUncertain(true);
    } catch {if (mounted.current) setUncertain(true);}
    finally {inFlight.current = false; if (mounted.current) setPending(false);}
  };
  const toggle = (id: string, path: string, checked: boolean) => setSelection((previous) => {
    const next = {...previous};
    if (checked && Object.keys(next).length < 100) next[id] = path;
    else if (!checked) delete next[id];
    return next;
  });
  const applied = command?.result?.status === "applied";
  return <section className="cataloging-review" aria-label="Revisar e catalogar">
    <header className="review-actions"><div><h3>Revisar candidatos</h3><p>Escolha até 100 itens por lote. A seleção é mantida entre páginas.</p></div>
      <button className="primary-button" disabled={submitted || pending || !page.items.some((item) => item.selectable)} onClick={() => {
        setSelection((previous) => {const next = {...previous}; for (const item of page.items) if (item.selectable && Object.keys(next).length < 100) next[item.candidate_id] = item.relative_path; return next;});
      }}>Selecionar elegíveis desta página</button>
    </header>
    <p role="status">{count} selecionado(s) de no máximo 100</p>
    {count > 0 && <details><summary>Revisar seleção ({count})</summary><ul className="review-selection">{Object.entries(selection).map(([id, path]) => <li key={id}>{path} <button disabled={submitted || pending} onClick={() => toggle(id, path, false)}>Remover</button></li>)}</ul></details>}
    <div className="cataloging-table"><table><caption>Candidatos — escolha explícita para catalogação</caption><thead><tr><th>Escolher</th><th>Caminho relativo</th><th>Verificação</th></tr></thead><tbody>{page.items.map((item) => <tr key={item.candidate_id}><td><input type="checkbox" aria-label={`Selecionar ${item.relative_path}`} checked={!!selection[item.candidate_id]} disabled={!item.selectable || submitted || pending || (count >= 100 && !selection[item.candidate_id])} onChange={(event) => toggle(item.candidate_id, item.relative_path, event.target.checked)} /></td><td>{item.relative_path}</td><td>{item.state === "eligible" && item.selectable === false ? "Já conhecido no catálogo" : reasonLabels[item.reason] ?? item.reason}</td></tr>)}</tbody></table></div>
    <div className="review-actions"><button className="primary-button" disabled={!count || submitted || pending} onClick={() => void apply()}>{pending ? "Aguardando confirmação…" : "Catalogar selecionados"}</button><span>Uma confirmação nativa será solicitada. Os originais permanecem inalterados.</span></div>
    {command && !done(command) && !uncertain && <p role="status">Catalogando — aguarde a conclusão. Fechar ou perder a resposta não comprova rollback.</p>}
    {(uncertain || command?.state === "outcome_unknown") && <div role="alert"><h3>Resultado incerto</h3><p>A operação pode ter gravado no catálogo. Nenhum pedido será repetido automaticamente. Feche e reabra a biblioteca; prepare novamente a pasta para verificar os caminhos registrados.</p></div>}
    {applied && !uncertain && <div className="cataloging-result" role="status"><h3>Catalogação concluída</h3><p>{command!.result!.items.filter((item) => item.disposition === "created").length} item(ns) adicionado(s). A biblioteca foi atualizada. Nenhum original foi movido ou modificado. Para outro lote, prepare novamente a pasta.</p>{onShowLibrary && <button className="primary-button" onClick={onShowLibrary}>Ver itens na biblioteca</button>}</div>}
    {command?.state === "completed" && !applied && <div role="alert"><h3>Catalogação não concluída</h3><p>{command.result?.status === "conflict" ? "O catálogo mudou depois da revisão." : "O lote foi bloqueado ou revertido."} Selecione novamente a pasta e prepare uma nova proposta antes de tentar outro lote.</p></div>}
  </section>;
}
