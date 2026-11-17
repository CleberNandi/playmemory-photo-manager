import { useRef, useState } from "react";
import type { MediaDevices, MediaImportResult } from "./types";

export function MediaDevicesPanel({
  onImported,
  onNotice,
}: {
  onImported?: (result: MediaImportResult) => void;
  onNotice?: (notice: { text: string; error?: boolean; persistent?: boolean }) => void;
} = {}) {
  const [result, setResult] = useState<MediaDevices>();
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [organizeByDate, setOrganizeByDate] = useState(false);
  const pending = useRef(false);

  function notify(text: string, error = false, persistent = false) {
    if (onNotice) {
      onNotice({ text, error, persistent });
    } else {
      setImportStatus(text);
    }
  }

  async function refresh() {
    if (pending.current || importing) return;
    pending.current = true;
    setBusy(true);
    try {
      setResult(await window.photoManager!.listMediaDevices!());
    } catch {
      setResult({status: "unavailable"});
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  async function importFrom(deviceId: string | null = null) {
    if (pending.current || importing || !window.photoManager?.importMediaFromDevice) return;
    setImporting(true);
    notify("Importando mídia para a biblioteca…", false, true);
    try {
      const imported = await window.photoManager.importMediaFromDevice(deviceId, organizeByDate);
      if (imported.status === "cancelled") {
        notify("Importação cancelada.");
      } else if (imported.status === "ready") {
        if (onImported) {
          onImported(imported);
        } else {
          notify(
            imported.copiedCount > 0
              ? `${imported.copiedCount} arquivo(s) copiado(s) · ${imported.catalogedCount} catalogado(s).`
              : imported.skippedCount > 0
                ? `Nenhuma foto nova (${imported.skippedCount} já existente(s) no destino).`
                : "Nenhuma imagem compatível encontrada na origem."
          );
        }
      } else {
        notify("Não foi possível concluir a importação.", true);
      }
    } catch {
      notify("Não foi possível concluir a importação.", true);
    } finally {
      setImporting(false);
    }
  }

  return <>
    <button className="nav-item" disabled={busy || importing} onClick={() => void refresh()}>
      {busy ? "Detectando dispositivos…" : result ? "Atualizar dispositivos" : "Detectar dispositivos"}
    </button>
    {window.photoManager?.importMediaFromDevice && (
      <>
        <label className="device-organize-toggle">
          <input type="checkbox" checked={organizeByDate} disabled={busy || importing} onChange={event => setOrganizeByDate(event.target.checked)} />
          Organizar por data (AAAA/MM)
        </label>
        <button className="nav-item" disabled={busy || importing} onClick={() => void importFrom(null)}>
          {importing ? "Importando…" : "Importar de pasta/câmera…"}
        </button>
      </>
    )}
    {!onNotice && importStatus && <p role="status">{importStatus}</p>}
    {result?.status === "ready" && (result.devices.length ? <>
      <ul className="media-devices">{result.devices.map(device =>
        <li key={device.id}>
          <strong>{device.name}</strong>
          <span>{device.kind === "imaging" ? "Dispositivo de imagem USB" : "Mídia removível ou armazenamento USB"}</span>
          {window.photoManager?.importMediaFromDevice && (
            <button type="button" disabled={busy || importing} onClick={() => void importFrom(device.id)}>
              Importar…
            </button>
          )}
        </li>
      )}</ul>
      {result.total_count > result.devices.length && <p>Exibindo {result.devices.length} de {result.total_count} dispositivos.</p>}
    </> : <p role="status">Nenhum dispositivo compatível detectado.</p>)}
    {result?.status === "unsupported" && <p role="status">A detecção de dispositivos está disponível no Linux.</p>}
    {result?.status === "unavailable" && <p role="status">Não foi possível consultar os dispositivos conectados.</p>}
  </>;
}
