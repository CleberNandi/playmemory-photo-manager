import {useEffect, useRef, useState} from "react";
import type {Album} from "./types";

export function AlbumPanel({active, selected, picking, onOpen, onBack, onRename, onDelete, onAdded, onRemoved}: {
  active?: Album;
  selected?: string | null;
  picking?: string;
  onOpen: (album: Album) => void;
  onBack?: () => void;
  onRename?: (album: Album) => void;
  onDelete?: () => void;
  onAdded?: () => void;
  onRemoved?: () => void;
}) {
  const api = window.photoManager!;
  const [albums, setAlbums] = useState<Album[]>([]);
  const [offset, setOffset] = useState<number | null>(null);
  const [action, setAction] = useState<"create" | "rename" | "delete" | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(!active);
  const [feedback, setFeedback] = useState<{text: string; error?: boolean}>();
  const pending = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => { if (picking) heading.current?.focus(); }, [picking]);
  useEffect(() => {
    if (active) return;
    let live = true;
    api.listAlbums!(0).then(page => {
      if (!live) return;
      setAlbums(page.albums);
      setOffset(page.next_offset);
    }).catch(() => {
      if (live) setFeedback({text:"Não foi possível carregar os álbuns.", error:true});
    }).finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [active, api]);

  async function run(task: () => Promise<void>) {
    if (pending.current || busy) return;
    pending.current = true;
    setBusy(true);
    setFeedback(undefined);
    try { await task(); }
    catch { setFeedback({text:"Não foi possível concluir a ação no catálogo.", error:true}); }
    finally { pending.current = false; setBusy(false); }
  }

  function start(mode: "create" | "rename" | "delete") {
    setName(mode === "rename" ? active?.name ?? "" : "");
    setAction(mode);
    setFeedback(undefined);
  }

  async function save() {
    const value = name.trim();
    if (!value) return;
    if (action === "rename" && active) {
      onRename?.(await api.renameAlbum!(active.id, value));
    } else {
      const album = await api.createAlbum!(value);
      const page = await api.listAlbums!(0);
      setAlbums(page.albums.some(item => item.id === album.id) ? page.albums : [album, ...page.albums]);
      setOffset(page.next_offset);
      setFeedback({text:"Álbum criado."});
    }
    setAction(null);
  }

  return <section className={active ? "album-panel album-actions" : "album-panel collection-page"} aria-label={picking ? "Adicionar a álbum" : "Gerenciar álbuns"} aria-busy={busy}>
    <div className="collection-actions">
      {picking && <h2 ref={heading} tabIndex={-1}>Adicionar a álbum</h2>}
      {onBack && <button className="primary-button" onClick={onBack}>{picking ? "Fechar" : "Voltar aos álbuns"}</button>}
      {!active && action !== "create" && <button className="primary-button" disabled={busy} onClick={() => start("create")}>Novo álbum</button>}
      {active && api.renameAlbum && <button className="primary-button" disabled={busy} onClick={() => start("rename")}>Renomear álbum</button>}
      {active && selected && <button className="primary-button" disabled={busy} onClick={() => void run(async () => {
        await api.changeAlbumMembership!(active.id, selected, "remove");
        onRemoved?.();
        setFeedback({text:"Item removido do álbum."});
      })}>Remover do álbum</button>}
      {active && api.deleteAlbum && <button className="primary-button" disabled={busy} onClick={() => start("delete")}>Excluir álbum</button>}
    </div>
    {(action === "create" || action === "rename") && <form className="collection-form" onSubmit={event => {event.preventDefault();void run(save);}}>
      <label>Nome do álbum<input autoFocus maxLength={120} value={name} onChange={event => setName(event.target.value)} /></label>
      <button className="primary-button" disabled={busy || !name.trim()}>{action === "rename" ? "Salvar nome" : "Criar álbum"}</button>
      <button className="primary-button" type="button" disabled={busy} onClick={() => setAction(null)}>Cancelar</button>
    </form>}
    {action === "delete" && active && <fieldset disabled={busy}>
      <legend>Excluir o álbum “{active.name}”?</legend>
      <p>As fotos permanecem na biblioteca.</p>
      <button className="primary-button" onClick={() => void run(async () => {
        await api.deleteAlbum!(active.id);
        onDelete?.();
      })}>Confirmar exclusão</button>
      <button className="primary-button" onClick={() => setAction(null)}>Cancelar</button>
    </fieldset>}
    {!active && albums.length > 0 && <ul className="collection-grid">
      {albums.map(album => <li key={album.id}>
        <button className="collection-card" disabled={busy} onClick={() => {
          if (!picking) {onOpen(album);return;}
          void run(async () => {
            const result = await api.changeAlbumMembership!(album.id, picking, "add");
            onAdded?.();
            setFeedback({text:result.changed ? `Item adicionado a “${album.name}”.` : `O item já está em “${album.name}”.`});
          });
        }}>{album.name}</button>
      </li>)}
    </ul>}
    {!active && !busy && !feedback?.error && !albums.length && <p>Nenhum álbum criado.</p>}
    {offset !== null && <button className="primary-button" disabled={busy} onClick={() => void run(async () => {
      const page = await api.listAlbums!(offset);
      setAlbums(previous => [...new Map([...previous, ...page.albums].map(album => [album.id, album])).values()]);
      setOffset(page.next_offset);
    })}>Carregar mais álbuns</button>}
    {feedback && <p role={feedback.error ? "alert" : "status"}>{feedback.text}</p>}
  </section>;
}
