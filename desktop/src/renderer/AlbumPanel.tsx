import {useEffect, useRef, useState} from "react";
import type {Album} from "./types";

export function AlbumPanel({active, selected, onOpen, onMembershipChanged}: {
  active: Album | null;
  selected: string | null;
  onOpen: (album: Album) => void;
  onMembershipChanged: (albumId: string, assetId: string, action: "add" | "remove") => void;
}) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [offset, setOffset] = useState<number | null>(0);
  const [target, setTarget] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(true);
  const [feedback, setFeedback] = useState<{text: string; error?: boolean}>();
  const pending = useRef(false);
  const bridge = window.photoManager!;

  useEffect(() => {
    let cancelled = false;
    pending.current = true;
    bridge.listAlbums!(0).then(page => {
      if (cancelled) return;
      setAlbums(page.albums);
      setOffset(page.next_offset);
    }).catch(() => {
      if (!cancelled) setFeedback({text:"Não foi possível carregar os álbuns.", error:true});
    }).finally(() => {
      if (!cancelled) {pending.current = false; setBusy(false);}
    });
    return () => {cancelled = true;};
  }, [bridge]);

  async function run(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setFeedback(undefined);
    try {await action();}
    catch {setFeedback({text:"Não foi possível concluir a ação no catálogo.", error:true});}
    finally {pending.current = false; setBusy(false);}
  }

  const chosen = albums.find(album => album.id === target);
  async function membership(album: Album, assetId: string, action: "add" | "remove") {
    const {changed} = await bridge.changeAlbumMembership!(album.id, assetId, action);
    if (changed) onMembershipChanged(album.id, assetId, action);
    setFeedback({text: action === "remove" ? "Item removido do álbum."
      : changed ? "Item adicionado ao álbum." : "Este item já faz parte do álbum."});
  }

  return <section className="album-panel" aria-label="Gerenciar álbuns">
    <form onSubmit={event => {
      event.preventDefault();
      void run(async () => {
        const album = await bridge.createAlbum!(name.trim());
        setAlbums(previous => [...previous, album]);
        if (offset !== null) setOffset(0);
        setTarget(album.id);
        setName("");
        setFeedback({text:"Álbum criado."});
      });
    }}>
      <label>Nome do álbum <input maxLength={120} value={name} onChange={event => setName(event.target.value)} /></label>
      <button disabled={busy || !name.trim()}>Criar álbum</button>
    </form>
    <label>Álbum <select value={target} onChange={event => setTarget(event.target.value)}>
      <option value="">Selecione</option>
      {albums.map(album => <option key={album.id} value={album.id}>{album.name}</option>)}
    </select></label>
    <button disabled={busy || !chosen} onClick={() => {if (chosen) onOpen(chosen);}}>Abrir álbum</button>
    <button disabled={busy || !chosen || !selected} onClick={() => {
      if (chosen && selected) void run(() => membership(chosen, selected, "add"));
    }}>Adicionar item selecionado</button>
    {active && <button disabled={busy || !selected} onClick={() => {
      if (selected) void run(() => membership(active, selected, "remove"));
    }}>Remover item deste álbum</button>}
    {offset !== null && <button disabled={busy} onClick={() => void run(async () => {
      const page = await bridge.listAlbums!(offset);
      setAlbums(previous => [...new Map([...previous, ...page.albums].map(album => [album.id, album])).values()]);
      setOffset(page.next_offset);
    })}>{offset ? "Carregar mais álbuns" : "Carregar álbuns"}</button>}
    {feedback && <p role={feedback.error ? "alert" : "status"}>{feedback.text}</p>}
  </section>;
}
