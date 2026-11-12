type Root = {id: string; name: string};

export function FolderNavigation({roots, root, path, children, onBrowse, onList, onAdd}: {
  roots: Root[];
  root?: Root;
  path: string;
  children: string[];
  onBrowse: (id: string, path: string) => void;
  onList: () => void;
  onAdd?: () => void;
}) {
  const segments = path ? path.split("/") : [];
  const folders = root ? children.map(name => ({id:root.id, name, path:path ? `${path}/${name}` : name}))
    : roots.map(item => ({...item, path:""}));
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
    {!root && !folders.length && <><p>Nenhuma pasta cadastrada.</p>{onAdd && <button className="primary-button" onClick={onAdd}>Adicionar pasta</button>}</>}
    {folders.length > 0 && <>
      {root && <h2>Subpastas</h2>}
      <ul className="collection-grid">{folders.map(folder => <li key={folder.path || folder.id}>
        <button className="collection-card folder-card" onClick={() => onBrowse(folder.id, folder.path)}>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
          {folder.name}
        </button>
      </li>)}</ul>
    </>}
  </section>;
}
