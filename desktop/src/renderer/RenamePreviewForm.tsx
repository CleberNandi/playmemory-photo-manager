import {useRef, useState} from "react";
import type {AssetDetails, RenamePreview} from "./types";

const messages = {
  invalid_name: "Use um nome simples, sem separadores de pasta.",
  same_name: "O arquivo já tem esse nome.",
  name_taken: "Já existe um arquivo ou registro com esse nome na pasta.",
  source_unavailable: "A localização está indisponível ou mudou desde a catalogação.",
};

export function RenamePreviewForm({details}: {details: AssetDetails}) {
  const locations = details.locations.filter(location =>
    location.entry_type === "file" && location.availability === "present" && location.root_availability === "available");
  const [locationId, setLocationId] = useState(locations[0]?.id ?? "");
  const [stem, setStem] = useState("");
  const [result, setResult] = useState<RenamePreview>();
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const selected = locations.find(location => location.id === locationId);

  async function preview() {
    if (!selected || pending.current) return;
    pending.current = true;
    setBusy(true);
    setResult(undefined);
    setError(false);
    try {
      setResult(await window.photoManager!.previewFileRename!(details.asset.id, selected.id, stem));
    } catch {
      setError(true);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  if (!locations.length) return null;
  return <details className="rename-preview">
    <summary>Prévia de renomeação</summary>
    <form onSubmit={event => {event.preventDefault(); void preview();}}>
      <fieldset disabled={busy}>
        <label>Localização
          <select value={locationId} onChange={event => {setLocationId(event.target.value); setResult(undefined); setError(false);}}>
            {locations.map(location => <option key={location.id} value={location.id}>
              {location.root_display_name} / {location.relative_path}
            </option>)}
          </select>
        </label>
        <label>Novo nome sem extensão
          <input value={stem} maxLength={255} onChange={event => {setStem(event.target.value); setResult(undefined); setError(false);}} />
        </label>
        <button disabled={!selected || !stem}>{busy ? "Verificando…" : "Verificar nome"}</button>
      </fieldset>
    </form>
    {error && <p role="alert">Não foi possível verificar o nome agora.</p>}
    {result?.status === "ready" && <div role="status">
      <p>Atual: {result.current_relative_path}</p>
      <p>Proposto: {result.proposed_relative_path}</p>
      <p>Prévia concluída. O arquivo continua com o nome atual.</p>
    </div>}
    {result && result.status !== "ready" && <p role="status">{messages[result.status]}</p>}
  </details>;
}
