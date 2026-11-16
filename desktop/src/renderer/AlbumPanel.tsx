import {useEffect, useRef, useState} from "react";
import type {Album} from "./types";

export function AlbumPanel({active, selected, picking, onOpen, onBack, onRename, onDelete, onAdded, onRemoved}: {
  active?: Album;
  selected?: string | string[] | null;
  picking?: string | string[];
  onOpen: (album: Album) => void;
  onBack?: () => void;
  onRename?: (album: Album) => void;
  onDelete?: () => void;
  onAdded?: () => void;
  onRemoved?: () => void;
}) {
  const api = window.photoManager!;
  const pickingIds = !picking ? [] : Array.isArray(picking) ? picking : [picking];
  const selectedIds = !selected ? [] : Array.isArray(selected) ? selected : [selected];
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
    if (!feedback || feedback.error) return;
    const timer = setTimeout(() => setFeedback(undefined), 4500);
    return () => clearTimeout(timer);
  }, [feedback]);
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
      setFeedback({text:"Álbum renomeado."});
    } else {
      const album = await api.createAlbum!(value);
      const page = await api.listAlbums!(0);
      setAlbums(page.albums.some(item => item.id === album.id) ? page.albums : [album, ...page.albums]);
      setOffset(page.next_offset);
      setFeedback({text:"Álbum criado."});
    }
    setAction(null);
  }

  return <section className={active ? "album-panel album-actions" : "album-panel collection-page"} aria-label={pickingIds.length ? "Adicionar a álbum" : "Gerenciar álbuns"} aria-busy={busy}>
    <div className="collection-actions">
      {pickingIds.length > 0 && <h2 ref={heading} tabIndex={-1}>{pickingIds.length > 1 ? `Adicionar ${pickingIds.length} itens a álbum` : "Adicionar a álbum"}</h2>}
      {onBack && <button className="primary-button" onClick={onBack}>{pickingIds.length ? "Fechar" : "Voltar aos álbuns"}</button>}
      {!active && action !== "create" && <button className="primary-button" disabled={busy} onClick={() => start("create")}>Novo álbum</button>}
      {active && api.renameAlbum && <button className="primary-button" disabled={busy} onClick={() => start("rename")}>Renomear álbum</button>}
      {active && selectedIds.length > 0 && <button className="primary-button" disabled={busy} onClick={() => void run(async () => {
        for (const id of selectedIds) await api.changeAlbumMembership!(active.id, id, "remove");
        onRemoved?.();
        setFeedback({text: selectedIds.length > 1 ? `${selectedIds.length} itens removidos do álbum.` : "Item removido do álbum."});
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
          if (!pickingIds.length) {onOpen(album);return;}
          void run(async () => {
            let changedCount = 0;
            for (const id of pickingIds) {
              const result = await api.changeAlbumMembership!(album.id, id, "add");
              if (result.changed) changedCount++;
            }
            onAdded?.();
            setFeedback({
              text: pickingIds.length === 1
                ? (changedCount > 0 ? `Item adicionado a “${album.name}”.` : `O item já está em “${album.name}”.`)
                : changedCount === pickingIds.length
                  ? `${changedCount} itens adicionados a “${album.name}”.`
                  : changedCount > 0
                    ? `${changedCount} de ${pickingIds.length} itens adicionados a “${album.name}”.`
                    : `Os ${pickingIds.length} itens já estão em “${album.name}”.`,
            });
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
    {feedback && <div className={`action-toast${feedback.error ? " action-toast-error" : ""}`} role={feedback.error ? "alert" : "status"}>
      <span>{feedback.text}</span>
      <button type="button" className="toast-dismiss" aria-label="Fechar mensagem" onClick={() => setFeedback(undefined)}>×</button>
    </div>}
  </section>;
}
