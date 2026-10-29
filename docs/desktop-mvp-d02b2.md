# Desktop MVP D02B-2 — thumbnails sintéticos

Implementado na branch `feat/desktop-mvp-d02b2`, sobre `main` em `3c5b168`.
Consolidação e publicação autorizadas em 2026-10-29, sem merge ou início de D02C.

## Contrato e isolamento

Fluxo: React → preload `getThumbnail(assetId)` → IPC `thumbnail:get` → ponte autenticada
JSON-lines `thumbnail.get`, com params exatamente `{asset_id: UUID canônico}`.
Resposta: `null` para indisponibilidade ou objeto `{media_type: "image/png", width: 256,
height: 160, base64: string}`. IDs inexistentes retornam `null`; entradas inválidas falham.
Não há paths, URLs externas, listener HTTP, leitura de originais ou persistência das imagens.
O renderer não escolhe modo nem catálogo. Somente o bootstrap Python `--demo` habilita a
resolução, sobre a conexão demo criada em memória; `--catalog` é mutuamente exclusivo.
Mesmo um UUID existente retorna `null` no modo normal. A consulta usa parâmetro SQL.

Foi revisado `gallery-read-model.md`: `SyntheticThumbnailStore` lê fixtures confinadas em disco,
com variante e referência opaca. Continua inalterado. Este incremento autorizado pelo pedido
corrente acrescenta apenas um adapter desktop demo em memória, sem promover o gerador a API de
produção, sem alterar schema ou semântica de referências/derivados do catálogo.
A skill Postman api-engineer orientou contrato e verificação; não houve necessidade de serviço,
workspace remoto ou coleção HTTP para esta ponte local JSON-lines.

## Geração e limites

`desktop/demo.py` mantém os UUIDs e os 73 Assets existentes. O gerador produz gráficos RGB com
faixas, círculos, paletas derivadas de SHA-256 do UUID e marcador de vídeo. São ilustrações,
identificadas visualmente por “Sintética” e no texto acessível; não alegam representar os Assets.
Usa apenas `hashlib`, `struct` e `zlib` da biblioteca padrão. Nunca abre mídia ou cache.
O digest escolhe cores, sem atuar como identidade de Asset ou evidência de conteúdo original.

PNG fixo 256×160, limite binário de 12 KiB, Base64 de até 16 KiB. Base64 custa aproximadamente
33% a mais, além das cópias de strings no JSON/IPC e do bitmap decodificado (cerca de 160 KiB
RGBA por card). É aceitável para 73 imagens pequenas e evita protocolo/servidor/cache novos.
O gerador verifica o limite binário; o renderer verifica tipo, dimensões, sintaxe e tamanho de
Base64 antes de criar `data:image/png`. O limite não substitui um decoder de mídia real.
O supervisor limita seu buffer de resposta a 256 KiB; requisições Python continuam em 64 KiB.

A fila React aceita até 73 tarefas pendentes e executa no máximo quatro chamadas simultâneas.
O handler Electron também limita a quatro e rejeita excesso, mantendo fallback no card.
A geração Python é serial, limitada a 40.960 pixels por imagem. Não há cache persistente.
Desmontar/remove o card cancela tarefas ainda na fila; chamadas já enviadas terminam, mas seu
callback fica inativo. O estado da imagem carrega o UUID para impedir apresentação no card errado.
Erros IPC, payload inválido e erro de decode mantêm placeholder e não derrubam a galeria.
`object-fit: contain` preserva proporções. Paginação e identidade visual foram preservadas.

## Evidências em 2026-10-29

| Verificação | Resultado |
| --- | --- |
| `uv sync --locked` com cache temporário | PASS |
| `uv run pytest` | 280 testes passaram |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS |
| `pnpm install --frozen-lockfile` | PASS, lockfile preservado |
| `pnpm build`, `pnpm typecheck`, `pnpm lint` | PASS |
| `pnpm test` | 27 testes passaram |
| Diff e whitespace de arquivos novos | PASS |
| `env -u ELECTRON_RUN_AS_NODE pnpm smoke:demo` | PASS, KDE Wayland real |
| `env -u ELECTRON_RUN_AS_NODE pnpm smoke` | PASS, modo normal vazio |

Testes Python cobrem todos os 73 PNGs distintos, determinismo, dimensões, conteúdo RGB descomprimido,
limites, UUIDs inválidos/inexistentes, modo normal mesmo com catálogo populado, entrada por protocolo,
distinção foto/vídeo e proibição de abertura de arquivos no caminho de geração.
Testes React verificam concorrência, cancelamento de fila, resposta atrasada em card reutilizado,
erros síncronos IPC, validação de payload e fallback após erro de imagem. Testes anteriores
continuam cobrindo paginação/retry e lifecycle do supervisor.

O smoke usa preload, IPC, Python e catálogo reais. Em cada página verifica a ordem exata dos Assets
mais `complete`, `naturalWidth === 256` e `naturalHeight === 160` de todas as imagens:

```text
SMOKE thumbnails PASS: 24 decoded PNGs
SMOKE pagination PASS: 24 cards, exact backend order
SMOKE thumbnails PASS: 48 decoded PNGs
SMOKE pagination PASS: 48 cards, exact backend order
SMOKE thumbnails PASS: 72 decoded PNGs
SMOKE pagination PASS: 72 cards, exact backend order
SMOKE thumbnails PASS: 73 decoded PNGs
SMOKE pagination PASS: 73 cards, exact backend order
```

Também valida quatro tamanhos de janela, ausência de Node no renderer, allowlist do preload,
privacidade na árvore acessível, falha do backend e recuperação real. Após restart, exige novamente
24 imagens decodificadas. Mantidos `sandbox: true`, `contextIsolation: true`, `nodeIntegration: false`.
Captura temporária `/tmp/playmemories-d02b2-gallery.png` inspecionada visualmente: gráficos variados,
fotos/vídeos identificados, sem distorção e sem alteração da estrutura dos cards. Não versionada.

## Limitações e próximos passos

O install pnpm precisou acesso ao store fora do sandbox do agente; o smoke gráfico também foi
executado fora dele, preservando o sandbox Electron. Avisos de gerenciamento de cor Wayland
persistem, sem falha funcional observada. Uma falha inicial de lint por ordenação de imports e
uma extensão incorreta de teste JSX foram corrigidas antes dos gates finais.

Sem thumbnails reais, acesso a mídia pessoal, decoder externo, cache, invalidação, jobs ou benchmark
de grande escala. Imagens são regeneradas na remontagem; a galeria incremental mantém as imagens
carregadas em memória e não é virtualizada. Uma falha isolada mantém fallback até remontar/reabrir;
não há retry automático ilimitado. A fila serve o catálogo demo pequeno, sem política de prioridade
por viewport. Multiplataforma e empacotamento continuam sem homologação adicional.
Evolução de thumbnails reais exige contrato próprio e autorização posterior.

## Homologação e publicação

O solicitante informou aprovação independente Gemini `PASS`, sem achados BLOCKER, MAJOR ou
MINOR, para a implementação consolidada neste incremento. O parecer completo não está
versionado; este registro atribui a aprovação à informação fornecida pelo solicitante.
A conferência do diff completo, incluindo os quatro arquivos novos, confirmou o escopo demo:
geração e transporte limitados, componentes React, testes e documentação. Nenhum contrato de
domínio ou schema foi alterado.

A publicação usa três commits coesos: geração/transporte, apresentação/testes React e documentação.
A PR tem base `main` em `3c5b168`; não há autorização para merge automático. Artefatos ignorados,
node_modules, dist, caches e screenshots temporárias ficam excluídos dos commits.
Os gates foram executados novamente nesta consolidação; os resultados após os commits também
serão registrados na PR. A tentativa inicial de smoke dentro do sandbox do agente falhou por
restrição do ambiente; a execução gráfica ocorre fora dele, mantendo o sandbox Electron.
