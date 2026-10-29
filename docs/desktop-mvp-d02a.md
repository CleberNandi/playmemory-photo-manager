# Desktop MVP D02A — UI/UX e estabilização do shell (D02A-R)

## Escopo entregue

A direção visual D02A foi preservada: tokens, sidebar compacta abaixo de 860 px, cabeçalho,
estados de biblioteca e cards com placeholders. Busca, importação, thumbnails, seleção,
visualizador, catálogo persistente e D02B continuam fora deste incremento.

D02A-R corrige a execução e os achados de acessibilidade sem mudar os DTOs, canais IPC ou o
protocolo Python definidos no D01:

- `preload.cts` é compilado pelo TypeScript para `dist/main/preload.cjs`. O preload sandboxed
  usa CommonJS e expõe somente `listGallery` e `retryGallery`;
- `contextIsolation: true`, `sandbox: true` e `nodeIntegration: false` continuam habilitados;
- aquisição da ponte e chamadas são feitas em uma função assíncrona. Ausência do preload,
  exceções síncronas e rejeições chegam ao estado de erro com retry, sem janela em branco;
- a nota de privacidade compacta usa recorte visual, preservando texto na árvore acessível;
- disponibilidade offline usa `#865715`. Foco usa esse tom no canvas e `#e0aa56` na sidebar;
  testes calculam luminância sRGB: texto ≥ 4,5:1 e foco ≥ 3:1 nas superfícies adjacentes;
- a altura do estado vazio desconta cabeçalho e padding também em janelas baixas;
- título e caminho passam por `trim`, com fallback de título para caminho e depois “Sem título”;
- nomes via `aria-label` foram removidos de containers genéricos. Cards informativos não entram
  no tab order; título, tipo e disponibilidade permanecem disponíveis como conteúdo semântico.

`jsdom` é uma dependência exclusiva de testes do DOM React; não integra o renderer distribuído.
Nenhuma dependência de UI, fonte externa ou flag gráfica permanente foi adicionada.

## Validação executada em 2026-10-28

Ambiente: Arch Linux, KDE Wayland, Electron 45.0.0, Node 24.22.0 e Python 3.14.8.
Baseline `main`/HEAD: `e014edd`; alterações mantidas em `feat/desktop-mvp-d02a`, sem commit.

| Verificação | Resultado |
| --- | --- |
| `uv sync --locked` com `UV_CACHE_DIR=/tmp/playmemories-uv-cache` | PASS |
| `uv run pytest` com o mesmo cache | 269 testes passaram |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS, 84 arquivos |
| `pnpm install --frozen-lockfile` em `desktop` | PASS |
| `pnpm build`, `pnpm typecheck`, `pnpm lint` em `desktop` | PASS |
| `pnpm test` em `desktop` | 23 testes, 4 arquivos, PASS |
| `git diff --check` e whitespace de cada arquivo novo | PASS |
| Smoke da janela normal e ponte real | PASS, exit 0 |

Os testes React cobrem loading, biblioteca vazia/populada, rejeição IPC, exceção síncrona,
ausência da ponte, retry bem-sucedido e retry que falha. Os componentes cobrem metadados vazios,
texto de disponibilidade, semântica e ausência de foco artificial; testes de contraste usam o CSS.

Para reproduzir o smoke, em uma sessão gráfica local:

```bash
cd desktop
env -u ELECTRON_RUN_AS_NODE pnpm smoke
```

O smoke executa o build de produção com o preload do produto e o backend Python real, sem mocks,
preload externo, offscreen ou `--no-sandbox`. O catálogo padrão é sintético, em memória; nenhum
original ou sidecar é aberto ou modificado. O teste:

1. aguarda a biblioteca vazia, chama `window.photoManager.listGallery` no renderer e verifica
   a allowlist da ponte e ausência de `process`/`require` no mundo principal;
2. redimensiona a janela para 1180×760, 860×560, 760×560 e 760×520, verifica ausência de overflow
   horizontal/vertical no estado vazio e encontra a nota de privacidade na árvore acessível
   Chromium via CDP;
3. encerra o Python, recarrega o renderer, verifica erro recuperável e clica no retry real;
4. abre o mesmo renderer em outra janela sem preload e verifica erro e retry sem crash.

Há timeout de 30 segundos e falha explícita em crash do renderer. Os limites da janela continuam
760×520; dimensões menores não constituem suporte do shell. A galeria populada foi validada em
DOM com DTOs sintéticos, sem introduzir catálogo populado ou interações futuras no produto.

Na execução final, um verificador externo consultou `/proc` antes e depois de aguardar a saída do
Electron: **zero processos da ponte Python antes e zero depois**. A saída confirmou os quatro
redimensionamentos e terminou com:

```text
SMOKE PASS: production preload → IPC → Python; resize; IPC failure; retry; missing preload
Backend processes after smoke: []
```

## Investigação ambiental e limitações

Foram separados três comportamentos:

- **Variável herdada:** com `ELECTRON_RUN_AS_NODE`, o binário roda como Node e falha no import de
  `BrowserWindow`. Remover essa variável somente do comando de validação permite iniciar Electron.
- **Sandbox do agente:** sem essa variável, mas dentro do ambiente restrito do agente, ocorre
  `FATAL: sandbox_host_linux.cc ... shutdown: Operation not permitted`, seguido de SIGTRAP.
  A execução gráfica foi repetida fora do sandbox do agente, mantendo o sandbox do produto.
- **Compositor:** fora do sandbox do agente, as execuções nominais passaram sem SIGTRAP e sem
  flags extras. Ainda há mensagens `wayland_wp_color_manager` e falha de descrição de espaço de
  cor. Elas não impediram a ponte, renderização, redimensionamento ou encerramento neste smoke.
  A captura anterior de D02A com preload temporário não é usada como evidência da ponte corrigida.

A falha IPC intencional gera `backend is not running` no stderr do processo principal; o renderer
mostra apenas mensagem sanitizada. O cache padrão de uv e o lock do store pnpm foram bloqueados
no sandbox do agente; sincronizações passaram fora dele, com cache temporário para uv.

O smoke curto não homologa estabilidade prolongada, fidelidade de cores, outras GPUs/compositores,
Windows/macOS, empacotamento ou o shell definitivo do ADR-004. Não foi aplicada mitigação permanente
para Wayland: os avisos remanescentes exigem investigação se produzirem defeito reproduzível.
