import {useRef, useState} from "react";
import type {AnnotationField, AssetDetails} from "./types";

export function AnnotationEditor({details, onUpdated}: {
  details: AssetDetails;
  onUpdated: (field: AnnotationField, value: string | number | null) => void;
}) {
  const [title, setTitle] = useState(details.annotation?.title ?? "");
  const [description, setDescription] = useState(details.annotation?.description ?? "");
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const pending = useRef(false);
  const rating = details.annotation?.rating ?? null;

  async function edit(field: AnnotationField, value: string | number | null) {
    if (pending.current || !window.photoManager?.editAnnotation) return;
    pending.current = true;
    setBusy(true);
    setMessage("");
    try {
      await window.photoManager.editAnnotation(details.asset.id, field, value);
      if (field === "tag_add") setTag("");
      setFailed(false);
      setMessage("Alteração salva no catálogo.");
      onUpdated(field, value);
    } catch {
      setFailed(true);
      setMessage("Não foi possível confirmar a alteração. Confira os dados antes de tentar novamente.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <section className="annotation-editor" aria-label="Organizar foto">
    <h3>Organização</h3>
    <fieldset disabled={busy}>
      <legend>Classificação por estrelas</legend>
      <div className="rating-buttons">
        {[1, 2, 3, 4, 5].map(stars => <button key={stars}
          aria-label={stars === 1 ? "1 estrela" : `${stars} estrelas`}
          aria-pressed={rating === stars}
          onClick={() => void edit("rating", stars)}>{stars <= (rating ?? 0) ? "★" : "☆"}</button>)}
      </div>
      {rating !== null && <button onClick={() => void edit("rating", null)}>Limpar avaliação</button>}
    </fieldset>
    <form onSubmit={event => {event.preventDefault(); void edit("tag_add", tag.trim());}}>
      <label>Tags <input value={tag} maxLength={100} onChange={event => setTag(event.target.value)} /></label>
      <button disabled={busy || !tag.trim()}>Adicionar tag</button>
    </form>
    {details.tags.length > 0 && <ul className="annotation-tags">{details.tags.map(item => <li key={item.id}>
      <span>{item.display_name}</span>
      <button aria-label={`Remover tag ${item.display_name}`} disabled={busy}
        onClick={() => void edit("tag_remove", item.id)}>Remover</button>
    </li>)}</ul>}
    <form onSubmit={event => {event.preventDefault(); void edit("title", title.trim() || null);}}>
      <label>Título <input value={title} maxLength={200} onChange={event => setTitle(event.target.value)} /></label>
      <button disabled={busy || title.trim() === (details.annotation?.title ?? "")}>Salvar título</button>
    </form>
    <form onSubmit={event => {event.preventDefault(); void edit("description", description.trim() || null);}}>
      <label>Descrição <textarea value={description} maxLength={2000} onChange={event => setDescription(event.target.value)} /></label>
      <button disabled={busy || description.trim() === (details.annotation?.description ?? "")}>Salvar descrição</button>
    </form>
    {message && <p role={failed ? "alert" : "status"}>{message}</p>}
  </section>;
}
