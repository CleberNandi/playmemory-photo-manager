# Desktop MVP D02B-1 — catálogo sintético e galeria paginada

Implementado sobre `main` em `8285a07`, na branch `feat/desktop-mvp-d02b1`.
Homologação independente Gemini informada pelo responsável: zero achados bloqueantes, major
ou minor. A publicação ocorre por PR para revisão, sem merge automático. D02B-2 não foi iniciado.

## Execução

Com as dependências Python e desktop já instaladas, na raiz:

```bash
uv sync --locked
cd desktop
pnpm install --frozen-lockfile
env -u ELECTRON_RUN_AS_NODE pnpm demo
```

`pnpm demo` faz build e inicia Electron com `PLAYMEMORIES_DESKTOP_DEMO=1`. O supervisor passa
`--demo` à ponte Python, inclusive após restart. `pnpm start` mantém o catálogo vazio em memória.
A variável só seleciona o modo no processo principal; o renderer não escolhe catálogo ou path.
O CLI Python rejeita a combinação de `--demo` com `--catalog`.

## Catálogo e identidade

`desktop/demo.py` cria exclusivamente uma conexão SQLite `:memory:` usando o inicializador,
schema e repositório existentes. Não recebe destinos, não abre catálogos em disco e não acessa
os paths sintéticos declarados nas raízes. Após popular, ativa `PRAGMA query_only=ON`.
Não há nova persistência, migração, modelo de catálogo ou serviço HTTP.

A fixture contém 73 Assets distintos (fotos e vídeos), 55 FileLocations e anotações com título,
favorito e rating opcional. Cobre `available`, `offline`, `unavailable` e `no_location`.
As raízes offline só contêm localizações offline; as localizações missing pertencem à raiz
available e representam uma ausência histórica sintética, não uma verificação física atual.
Nenhum arquivo de mídia é criado, lido ou alterado. Não há hashes alegados como verificados,
metadata extraída inventada ou datas de captura inferidas.

A fixture usa um PRNG local de seed fixa para UUIDs v4 independentes de paths e conteúdo.
Esse mecanismo é exclusivo da fixture, sem alterar a geração aleatória do domínio em produção.
IDs, anotações e estados são reproduzíveis entre inicializações; `created_at` é fixo para
exercitar o desempate por UUID. O histórico de migrações conserva seu instante real de execução.
O repositório existente popula as entidades e os estados históricos; os setters de `Catalog`
populam as anotações. Isso não adiciona uma API de transição para missing nem relaxa seus contratos.

## Paginação e recuperação

O fluxo é React → preload → IPC Electron → ponte Python → `GalleryQueries` → SQLite.
Os DTOs, canais e allowlist IPC existentes permanecem. Cada chamada pede 24 itens e passa o
`next_cursor` opaco sem reinterpretá-lo. A ordem continua `(created_at ASC, id ASC)`.
“Carregar mais” acrescenta a próxima página; uma trava impede chamadas simultâneas por clique
duplo. Após 24, 48, 72 e 73 itens, aparece “Fim da biblioteca”.

Loading inicial, vazio e erro inicial continuam disponíveis. Durante a próxima página, os cards
permanecem e o botão mostra loading. Falha mantém os cards e o cursor para nova tentativa;
“Reabrir biblioteca” reinicia o backend e volta à primeira página se o processo tiver caído.
Erros públicos não exibem detalhes internos. Cards mostram tipo, título/caminho relativo,
disponibilidade, media type, favorito e rating, com os placeholders D02A.

## Evidências em 2026-10-29

| Verificação | Resultado |
| --- | --- |
| `uv sync --locked` (`UV_CACHE_DIR` temporário) | PASS |
| `uv run pytest` | 272 testes passaram |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS |
| `pnpm install --frozen-lockfile` | PASS, sem alteração do lockfile |
| `pnpm build`, `pnpm typecheck`, `pnpm lint` | PASS |
| `pnpm test` | 24 testes passaram |
| `git diff --check` e whitespace de arquivos novos | PASS |
| Smoke gráfico populado e vazio | PASS |

Os testes novos verificam a igualdade dos dados de duas gerações independentes, integridade e
foreign keys SQLite, UUIDs v4, conexão somente leitura, isolamento do bootstrap, exclusão mútua
CLI e travessia completa via despacho da ponte em quatro páginas. O teste React verifica cursor,
falha intermediária sanitizada, preservação dos cards, retry, clique duplo, loading e fim.

Reprodução dos smokes na sessão gráfica:

```bash
cd desktop
env -u ELECTRON_RUN_AS_NODE pnpm smoke:demo
env -u ELECTRON_RUN_AS_NODE pnpm smoke
```

O smoke usa janela normal, preload de produção, Python e SQLite reais, sem mock ou `--no-sandbox`.
Verifica unicidade dos UUIDs no backend e compara os títulos únicos da fixture nos cards
renderizados com a sequência completa do backend em cada página, sem inserir UUIDs no HTML:

```text
SMOKE pagination PASS: 24 cards, exact backend order
SMOKE pagination PASS: 48 cards, exact backend order
SMOKE pagination PASS: 72 cards, exact backend order
SMOKE pagination PASS: 73 cards, exact backend order
SMOKE PASS: production preload → IPC → Python; pagination/empty; resize; IPC failure; retry; missing preload
```

Também verifica ausência de Node no renderer, allowlist do preload, ausência de overflow horizontal
e nota de privacidade na árvore acessível em 1180×760, 860×560, 760×560 e 760×520. O modo vazio
verifica também ausência de overflow vertical. A galeria usa rolagem vertical normal. Após encerrar
o Python, recarrega a janela, observa erro e aciona recuperação real. Uma janela sem preload
continua mostrando erro recuperável. O smoke demo salva captura temporária em
`/tmp/playmemories-d02b1-gallery.png`; ela foi inspecionada visualmente e não é versionada.

## Riscos e limites

A execução dentro do sandbox do agente falhou em `sandbox_host_linux.cc` com SIGTRAP.
Os smokes passaram fora dele, preservando `sandbox: true`, `contextIsolation: true` e
`nodeIntegration: false`. O install pnpm também exigiu acesso ao store fora do sandbox do agente.
Persistem avisos Wayland sobre gerenciamento de cor, sem defeito funcional observado neste smoke.

O catálogo é descartável, em memória e recriado no restart; não representa persistência de sessão.
A navegação é incremental por “Carregar mais”, sem voltar/substituir páginas ou virtualização:
memória do renderer cresce com os itens carregados. A garantia de não perder/repetir itens é para
catálogo estável; o read model não promete snapshot entre chamadas sob mutação concorrente.
Não houve benchmark de catálogos grandes; permanece o custo de ordenação documentado no read model.
Não há thumbnails, importação pessoal, detalhe de Asset, duplicatas ou operações de mídia.
O smoke curto não homologa outras plataformas, empacotamento, estabilidade prolongada ou o shell
definitivo do ADR-004.
