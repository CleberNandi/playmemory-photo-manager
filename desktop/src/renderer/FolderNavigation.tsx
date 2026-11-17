import { useState } from "react";

type Root = {id: string; name: string};

export function FolderNavigation({roots, root, path, children, onBrowse, onList, onAdd, onRemoveRoot}: {
  roots: Root[];
  root?: Root;
  path: string;
  children: string[];
  onBrowse: (id: string, path: string) => void;
  onList: () => void;
  onAdd?: () => void;
  onRemoveRoot?: (id: string) => Promise<void>;
}) {
  const [confirming, setConfirming] = useState<Root | null>(null);
  const [removing, setRemoving] = useState(false);
  const segments = path ? path.split("/") : [];
  const folders = root ? children.map(name => ({id:root.id, name, path:path ? `${path}/${name}` : name}))
    : roots.map(item => ({...item, path:""}));

  async function confirmRemove() {
    if (!confirming || !onRemoveRoot || removing) return;
    setRemoving(true);
    try {
      await onRemoveRoot(confirming.id);
      setConfirming(null);
    } finally {
      setRemoving(false);
    }
  }

  return <section className="collection-page folder-navigation" aria-label="Navegação de pastas">
    {root && <nav className="folder-breadcrumb" aria-label="Caminho da pasta">
      <button onClick={onList}>Pastas</button><span aria-hidden="true">›</span>
      {segments.length ? <button onClick={() => onBrowse(root.id, "")}>{root.name}</button> : <span aria-current="location">{root.name}</span>}
      {segments.map((name, index) => <span key={index}>
        <span aria-hidden="true">›</span>
        {index === segments.length - 1 ? <span aria-current="location">{name}</span>
          : <button onClick={() => onBrowse(root.id, segments.slice(0, index + 1).join("/"))}>{name}</button>}
      </span>)}
    </nav>}
    {root && !path && <p>Imagens desta pasta e de todas as subpastas.</p>}
    {!root && !folders.length && <><p>Nenhuma pasta cadastrada.</p>{onAdd && <button className="primary-button" onClick={onAdd}>Adicionar pasta</button>}</>}
    {!root && confirming && (
      <div className="folder-remove-confirm" role="region" aria-label="Confirmar remoção da pasta">
        <p>Desvincular <strong>{confirming.name}</strong> do catálogo? Os arquivos no disco não serão alterados.</p>
        <div className="duplicate-actions">
          <button type="button" className="primary-button" disabled={removing} onClick={() => void confirmRemove()}>
            {removing ? "Removendo…" : "Confirmar remoção"}
          </button>
          <button type="button" disabled={removing} onClick={() => setConfirming(null)}>Cancelar</button>
        </div>
      </div>
    )}
    {folders.length > 0 && <>
      {root && <h2>Subpastas</h2>}
      <ul className="collection-grid">{folders.map(folder => <li key={folder.path || folder.id}>
        <button className="collection-card folder-card" onClick={() => onBrowse(folder.id, folder.path)}>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
          {folder.name}
        </button>
        {!root && onRemoveRoot && (
          <button type="button" className="folder-remove-button" disabled={removing} onClick={() => setConfirming({id: folder.id, name: folder.name})}>
            Remover do catálogo…
          </button>
        )}
      </li>)}</ul>
    </>}
  </section>;
}
