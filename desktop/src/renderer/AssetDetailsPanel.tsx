import { useEffect, useRef, useState } from "react";
import { AvailabilityIndicator } from "./AvailabilityIndicator";
import { requestThumbnail } from "./thumbnails";
import type { AssetDetails, DetailsResult } from "./types";

export function AssetDetailsPanel({assetId, onClose}: {assetId: string; onClose: () => void}) {
  const [result, setResult] = useState<{id: string; value: DetailsResult} | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [thumbnail, setThumbnail] = useState<{id: string; url: string} | null>(null);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => { close.current?.focus(); }, []);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose]);
  useEffect(() => requestThumbnail(assetId, (url) => setThumbnail(url ? {id: assetId, url} : null)), [assetId]);
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        if (!window.photoManager?.getAssetDetails) throw new Error();
        const value = await window.photoManager.getAssetDetails(assetId);
        if (active) setResult({id: assetId, value});
      } catch { if (active) setResult({id: assetId, value: {status: "temporarily_unavailable"}}); }
    })();
    return () => { active = false; };
  }, [assetId, attempt]);
  const value = result?.id === assetId ? result.value : null;
  return <aside className="asset-details" aria-labelledby="details-heading">
    <header><h2 id="details-heading">Detalhes do Asset</h2><button ref={close} className="primary-button" onClick={onClose}>Fechar detalhes</button></header>
    <p className="section-kicker">Somente leitura</p>
    {!value && <p role="status">Carregando detalhes…</p>}
    {value?.status === "not_found" && <p role="status">Asset não encontrado no catálogo.</p>}
    {value && value.status !== "ready" && value.status !== "not_found" && <div role="alert"><p>{value.status === "internal_error" ? "Não foi possível interpretar os detalhes." : "Detalhes temporariamente indisponíveis."}</p><button className="primary-button" onClick={() => { setResult(null); void (async () => { try { if (value.status === "temporarily_unavailable") await window.photoManager?.retryGallery(); } catch { /* The details request presents the sanitized failure. */ } setAttempt((n) => n + 1); })(); }}>Tentar detalhes novamente</button><p>Tentar novamente reconecta o backend local quando necessário.</p></div>}
    {value?.status === "ready" && <>
      {thumbnail?.id === assetId && <figure><img className="details-thumbnail" src={thumbnail.url} alt="Ilustração sintética de demonstração" onError={() => setThumbnail(null)} /><figcaption>Miniatura sintética</figcaption></figure>}
      <DetailsContent details={value.details} />
    </>}
  </aside>;
}
function Fields({values}: {values: Record<string, string | number | boolean | null>}) {
  return <dl>{Object.entries(values).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value === null ? "Não informado" : typeof value === "boolean" ? value ? "Sim" : "Não" : String(value)}</dd></div>)}</dl>;
}
export function DetailsContent({details: d}: {details: AssetDetails}) {
  return <>
    <h3>{d.annotation?.title ?? "Sem título"}</h3>
    <AvailabilityIndicator availability={d.availability} /><p>Disponibilidade registrada no catálogo; sem verificação física atual.</p>
    <Fields values={{"Asset ID": d.asset.id, "Tipo": d.asset.kind, "Media type": d.asset.media_type, "Tamanho conhecido (bytes)": d.asset.byte_size, "Favorito": d.annotation?.favorite ?? null, "Rating (1–5)": d.annotation?.rating ?? null}} />
    <h3>Descrição e tags</h3><p className="preserve-text">{d.annotation?.description ?? "Sem descrição"}</p><p>{d.tags.length ? d.tags.map((tag) => tag.display_name).join(" · ") : "Sem tags"}</p>
    <h3>Informações temporais</h3><Fields values={{"Catalogado em (não é captura)": d.asset.created_at}} />
    {d.capture ? <Fields values={{"Captura local": d.capture.local_value, "Precisão": d.capture.precision, "Estado de timezone": d.capture.timezone_state, "Offset (minutos)": d.capture.offset_minutes, "Zona": d.capture.timezone_name, "Fonte": d.capture.source_kind, "Metadata selecionada": d.capture.metadata_id, "Motivo da seleção": d.capture.selection_reason}} /> : <p>Sem data de captura selecionada.</p>}
    <h3>Localizações conhecidas</h3>
    {!d.locations.length && <p>Sem localizações conhecidas.</p>}
    {d.locations_truncated && <p role="status">Localizações truncadas: exibindo somente as primeiras 100.</p>}
    <ul>{d.locations.map((location) => <li key={location.id}><Fields values={{"Raiz": location.root_display_name, "ID da raiz": location.library_root_id, "Caminho relativo": location.relative_path, "Estado da raiz": location.root_availability, "Estado da localização": location.availability, "Tipo de entrada": location.entry_type, "Tamanho observado (bytes)": location.observed_byte_size, "mtime observado (ns; não é captura)": location.observed_mtime_ns, "Última observação": location.last_seen_at}} /></li>)}</ul>
    <h3>Metadata extraída</h3>
    {d.metadata_state === "not_extracted" && <p>Metadata não extraída. Isso não indica ausência de metadata na mídia.</p>}
    {d.metadata.map((m) => <details key={m.id}><summary>{m.namespace}:{m.key}{m.is_conflicting ? " · Conflito preservado" : ""}</summary><Fields values={{"ID": m.id, "Fonte": m.source, "Chave de origem": m.source_key, "Valor bruto": m.raw_value, "Valor interpretado": m.interpreted_value, "Tipo": m.value_type, "Valor temporal local": m.temporal_local_value, "Precisão": m.temporal_precision, "Timezone": m.timezone_state, "Offset (minutos)": m.utc_offset_minutes, "Zona": m.timezone_name, "Extrator": m.extractor_version, "Extraído em": m.extracted_at, "Erro de parse": m.parse_error, "Grupo de conflito": m.conflict_group, "Conflitante": m.is_conflicting}} /></details>)}
    <details><summary>Diagnóstico do catálogo</summary><Fields values={{"Estado": d.asset.status, "Estado do hash": d.asset.hash_state, "SHA-256": d.asset.sha256, "Anotação criada": d.annotation?.created_at ?? null, "Anotação atualizada": d.annotation?.updated_at ?? null}} /></details>
  </>;
}
