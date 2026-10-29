# Desktop MVP D02C — detalhes read-only do Asset

Implementado em `feat/desktop-mvp-d02c`, sobre `main` em `6b500c4`.
Consolidação e publicação autorizadas em 2026-10-29, sem merge ou início de D03.

## Contrato e fronteiras

React chama `photoManager.getAssetDetails(assetId)` → preload → IPC allowlisted
`asset:details` → supervisor Python → JSON-lines autenticado `asset.details` com
params exatamente `{asset_id: UUID canônico}` → `GalleryQueries.get_asset_details()`.
Não há nova consulta SQL, modelo de domínio, persistência, migração ou serviço HTTP.
A skill Postman api-engineer foi consultada para contrato e testes; setup remoto e
coleção HTTP não acrescentariam cobertura à ponte local.

O resultado IPC é uma união com `status`: `ready` traz `details`; os demais estados
são `not_found`, `invalid_request`, `temporarily_unavailable` e `internal_error`.
Na ponte Python: `not_found` identifica inexistência, `invalid_request` entrada inválida,
`temporarily_unavailable` identifica SQLite busy/locked, e `backend_failure` falha interna.
No Electron, falha de processo, timeout e envio tornam-se indisponibilidade temporária;
`backend_failure` torna-se erro interno. O renderer recebe códigos e textos fixos,
sem mensagens de exceção ou causas internas. O retry temporário usa o restart existente
antes de consultar novamente, mantendo as páginas já carregadas.

A serialização deriva exclusivamente da dataclass pública `AssetDetails`, incluindo
null, estados, proveniência, conflitos e `locations_truncated`. Uma adaptação de transporte
preserva `observed_mtime_ns` como string decimal ou null: nanosegundos excedem o limite
inteiro exato de JavaScript. Os demais campos conservam os tipos JSON da projeção.
Não são enviados paths absolutos de LibraryRoot, conexão SQLite ou objetos de execução.
O limite existente de 100 localizações permanece; disponibilidade é o agregado da consulta,
não é recalculada somente com as localizações visíveis.

Mantidos sandbox Electron, contextIsolation, ausência de Node no renderer, CSP e bloqueios
de navegação/permissões. A seleção não abre mídia, arquivos ou sidecars, nem escreve no catálogo.

## Interação e apresentação

O título do card contém um botão nativo com área de clique estendida ao card: mouse,
Enter e Espaço ativam a seleção; Tab percorre os controles. `aria-pressed` anuncia seleção,
e há foco visível no card. O painel lateral nomeado é não modal: não prende foco, mantém
a galeria acessível e permite troca direta de Asset. Ao abrir, foca Fechar; Escape ou Fechar
restauram o foco no card originador. A largura responsiva reserva espaço na galeria, inclusive
na janela mínima 760×520, evitando controles cobertos por overlay. A largura não é ajustável
manualmente neste incremento.

Identidade/tipo, thumbnail sintética disponível, anotações, tamanho, disponibilidade,
localizações relativas, datas com precisão/fonte/timezone, descrição e tags são read-only.
Metadata e diagnóstico usam expansões nativas, com valores brutos, interpretação, extrator,
instante, erro de parse e conflito preservados. Sem timezone conhecido não há conversão ou
inferência. Data de catalogação e mtime são rotulados separadamente da captura.

Ausência de captura, descrição, tags, localizações e metadata tem texto explícito.
`not_extracted` informa que nenhuma extração foi registrada; não afirma ausência de EXIF/GPS
na mídia. Texto extenso quebra linha e preserva novas linhas; conteúdo é renderizado como texto
React, sem HTML interpretado. Loading, not-found e erro têm estados próprios.
Efeitos descartam respostas antigas na troca, fechamento e desmontagem. A galeria permanece
montada, preservando paginação e thumbnails.

## Fixture e cobertura

Os 73 Assets, UUIDs, ordenação e paginação permanecem intactos. A fixture existente já cobre
foto/vídeo, favorito independente de rating, ratings ausentes, localizações disponíveis,
offline, missing e nenhuma localização. Ela continua sem descrição/tags/metadata extraída;
optou-se por preservar essa demonstração de ausência em vez de inventar observações.
Fixtures isoladas de teste acrescentam 101 localizações e metadata explicitamente identificada
como laboratório sintético, com conflito, valores ausentes e proveniência. Não são incorporadas
ao catálogo demo nem apresentadas como observações de mídia real.

## Validação e evidências em 2026-10-29

Gates executados na árvore de trabalho, com `UV_CACHE_DIR=/tmp/playmemories-uv-cache`:

| Comando | Resultado |
| --- | --- |
| `uv sync --locked` | PASS |
| `uv run pytest` | PASS, 291 testes |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS |
| `pnpm build`, `pnpm typecheck`, `pnpm lint` em desktop | PASS |
| `pnpm test` em desktop | PASS, 33 testes |
| `git diff --check` e whitespace de arquivos novos | PASS |
| `env -u ELECTRON_RUN_AS_NODE pnpm smoke:demo` | PASS, Electron/Python reais, KDE Wayland |
| `env -u ELECTRON_RUN_AS_NODE pnpm smoke` | PASS, modo normal vazio |

Testes Python verificam serialização da projeção existente, UUID inválido/inexistente,
allowlist de params, ausência de escrita/paths absolutos, sanitização, busy versus erro interno,
truncamento, nanosegundos exatos e proveniência/conflito. Testes React verificam seleção,
loading, foco, Escape/fechamento, not-found, falha/reconexão, troca rápida, resposta antiga e
resposta após fechar/reabrir, texto extenso e ausência de metadata. As suítes existentes
continuam verificando paginação, thumbnails e lifecycle do supervisor.

O smoke real verifica as quatro páginas (24/48/72/73) na ordem exata e todas as PNGs decodificadas;
abertura por Enter e fechamento por Escape enviados ao Chromium; retorno de foco;
painel aberto em 1180×760, 860×560, 760×560 e 760×520 sem overflow horizontal;
allowlist, UUID inválido e inexistente; ausência de Node; privacidade na árvore acessível;
backend encerrado com erro de detalhes e recuperação por restart mantendo a galeria;
e falha/retry geral e janela sem preload. O modo normal valida biblioteca vazia e erros de
identificador, sem acessar dados pessoais.

Captura temporária `/tmp/playmemories-d02c-details.png` inspecionada visualmente: painel lateral,
miniatura sintética, seleção e foco visíveis, cards preservados. Não versionada.
As tentativas iniciais do smoke de teclado falharam porque a sequência injetada não incluía
o evento `char` de Enter; a sequência completa passou sem alteração da ativação nativa do botão.
A execução gráfica precisou sair do sandbox do agente, preservando o sandbox do Electron.
Avisos de gerenciamento de cor Wayland persistiram sem falha funcional observada.

## Limitações

Sem extração real, EXIF/GPS inventado, mídia original, edição, importação, operações de arquivo,
cache persistente ou novos serviços. Somente thumbnails sintéticas do modo demo estão disponíveis.
Metadata detalhada populada é validada por testes sintéticos, não por extração ou smoke visual
de arquivos reais. O transporte mantém o limite anterior de resposta de 256 KiB do supervisor;
um DTO excessivo falha fechado, sem truncamento silencioso nem aumento de limite.
Não há benchmark de catálogo grande, virtualização, redimensionamento manual do painel,
homologação multiplataforma. A aprovação independente informada pelo solicitante está registrada abaixo.

## Homologação e publicação

O solicitante informou aprovação independente Gemini `PASS`, sem achados BLOCKER, MAJOR ou
MINOR, para a implementação D02C. O parecer completo não está versionado; este registro atribui
a aprovação à informação fornecida pelo solicitante.

A conferência do diff completo, incluindo os quatro arquivos novos, confirmou o escopo homologado:
ponte read-only para `get_asset_details()`, seleção e painel acessível, testes e evidências.
Não houve mudança de contratos de domínio, schema, fixture ou implementação após a homologação.

A consolidação separa quatro commits: ponte/contrato IPC, painel React, testes/smoke e documentação.
A publicação da branch `feat/desktop-mvp-d02c` e a abertura de PR contra `main` em
`CleberNandi/playmemory-photo-manager` foram autorizadas. Não há autorização para merge automático.
Os gates serão reexecutados após os commits, e os resultados da revisão exata publicada serão
registrados na PR. A tabela anterior documenta a execução da implementação antes da consolidação.
Screenshots temporárias, caches, dist e dependências instaladas permanecem fora dos commits.
