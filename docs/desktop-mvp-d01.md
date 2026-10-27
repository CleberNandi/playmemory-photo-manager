# Desktop MVP D01 — shell Electron experimental

## Escopo e decisão

O D01 implementa a PoC prevista no ADR-004, sem homologar Electron como shell definitivo. O
renderer React acessa somente `window.photoManager.listGallery()`, exposto pelo preload. O processo
principal inicia um backend Python por `uv`, gera um segredo efêmero e troca mensagens JSON por
`stdio`; não existe listener de rede, HTTP ou acesso arbitrário ao filesystem.

O backend aceita apenas `gallery.list` e `shutdown`. A primeira operação delega para
`GalleryQueries` e não lê originais. Sem `--catalog`, o processo usa um catálogo SQLite sintético
em memória; um catálogo informado é aberto em modo somente leitura e precisa estar no schema 2.
Paths absolutos, conexão SQLite e detalhes internos de erro não atravessam a ponte.

## Execução no Arch Linux

Pré-requisitos desta PoC: Node.js 22+, pnpm 10+, Python 3.13+ e `uv` disponíveis no `PATH`.

```bash
uv sync --locked
cd desktop
pnpm install --frozen-lockfile
pnpm start
```

Para desenvolvimento com reload:

```bash
cd desktop
pnpm dev
```

O comando deve abrir uma janela com a Biblioteca e o estado vazio confirmado pelo backend. Fechar
a última janela solicita `shutdown`, aguarda o processo Python e escala para `SIGTERM`/`SIGKILL`
somente em timeout. Falha de bootstrap, crash ou timeout aparece como estado recuperável e
sanitizado na interface.

## Segurança e limitações verificáveis

- `contextIsolation`, sandbox do renderer e `nodeIntegration: false` estão habilitados;
- navegação e criação de novas janelas são negadas;
- o IPC Electron tem somente `gallery:list`; o protocolo Python também valida método, payload,
  tamanho, timeout e segredo de sessão;
- a galeria usa placeholders: thumbnails reais e resolução de mídia continuam fora do D01;
- não há seletor/lifecycle persistente de catálogo, empacotamento, instalação de Python embutido,
  métricas formais, Windows/macOS ou operações de catalogação;
- D02–D06 e o Duplicate Lab não são importados nem iniciados.
