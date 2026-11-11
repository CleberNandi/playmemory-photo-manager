import { useRef, useState } from "react";
import type { MediaDevices } from "./types";

export function MediaDevicesPanel() {
  const [result, setResult] = useState<MediaDevices>();
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);

  async function refresh() {
    if (pending.current) return;
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

  return <>
    <button className="nav-item" disabled={busy} onClick={() => void refresh()}>
      {busy ? "Detectando dispositivos…" : result ? "Atualizar dispositivos" : "Detectar dispositivos"}
    </button>
    {result?.status === "ready" && (result.devices.length ? <>
      <ul className="media-devices">{result.devices.map(device =>
        <li key={device.id}><strong>{device.name}</strong><span>{device.kind === "imaging" ? "Dispositivo de imagem USB" : "Mídia removível ou armazenamento USB"}</span></li>
      )}</ul>
      {result.total_count > result.devices.length && <p>Exibindo {result.devices.length} de {result.total_count} dispositivos.</p>}
    </> : <p role="status">Nenhum dispositivo compatível detectado.</p>)}
    {result?.status === "unsupported" && <p role="status">A detecção de dispositivos está disponível no Linux.</p>}
    {result?.status === "unavailable" && <p role="status">Não foi possível consultar os dispositivos conectados.</p>}
  </>;
}
