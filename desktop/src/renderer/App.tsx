import { useEffect, useState } from "react";
import type { GalleryPage } from "./types";

type State =
  | { kind: "loading" }
  | { kind: "ready"; page: GalleryPage }
  | { kind: "error" };

export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = () => {
    setState({ kind: "loading" });
    void window.photoManager
      .listGallery({ pageSize: 24 })
      .then((page) => setState({ kind: "ready", page }))
      .catch(() => setState({ kind: "error" }));
  };

  useEffect(() => {
    let active = true;
    void window.photoManager
      .listGallery({ pageSize: 24 })
      .then((page) => { if (active) setState({ kind: "ready", page }); })
      .catch(() => { if (active) setState({ kind: "error" }); });
    return () => { active = false; };
  }, []);

  return (
    <div className="shell">
      <aside>
        <div className="brand"><span>PM</span> PlayMemories</div>
        <nav aria-label="Principal">
          <button className="active">Biblioteca</button>
          <button disabled>Álbuns</button>
          <button disabled>Ferramentas</button>
        </nav>
        <p className="privacy">Local e offline<br />Seus originais não são alterados.</p>
      </aside>
      <main>
        <header>
          <div><p className="eyebrow">Sua coleção</p><h1>Biblioteca</h1></div>
          <span className="offline">● Operação local</span>
        </header>
        {state.kind === "loading" && <Status title="Abrindo o catálogo…" body="Conectando ao backend local seguro." />}
        {state.kind === "error" && <Status title="Não foi possível abrir a biblioteca" body="O backend local não respondeu. Nenhum arquivo foi alterado." action={load} />}
        {state.kind === "ready" && state.page.items.length === 0 && <Status title="Sua biblioteca está vazia" body="A comunicação com o catálogo está funcionando. A seleção e catalogação de pastas entram em um incremento futuro." />}
        {state.kind === "ready" && state.page.items.length > 0 && (
          <section className="grid" aria-label="Itens da biblioteca">
            {state.page.items.map((item) => (
              <article key={item.asset_id}>
                <div className="placeholder" aria-hidden="true">{item.kind === "video" ? "▶" : "◇"}</div>
                <h2>{item.annotation.title ?? item.representative_location?.relative_path ?? "Sem título"}</h2>
                <p>{item.availability}</p>
              </article>
            ))}
          </section>
        )}
      </main>
    </div>
  );
}

function Status({ title, body, action }: { title: string; body: string; action?: () => void }) {
  return <section className="status" role="status"><div className="status-icon">◇</div><h2>{title}</h2><p>{body}</p>{action && <button onClick={action}>Tentar novamente</button>}</section>;
}
