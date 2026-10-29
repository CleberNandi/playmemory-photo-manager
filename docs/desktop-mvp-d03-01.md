# Desktop MVP D03-01 — duplicatas exatas sintéticas, somente leitura

Data: 2026-10-29. Base: `main` em `b5eb8988c2a77d5a66197a816b31589f639a452f`.
Branch: `feat/desktop-mvp-d03-01`. Referência normativa: [D03-00](desktop-mvp-d03-00.md),
subordinada às ADR-001–004. Implementação local para auditoria; sem commit, push ou merge.

## Comportamento entregue

A navegação **Duplicatas exatas** apresenta grupos e membros de uma projeção exclusivamente
sintética. A galeria permanece montada, com seus itens, UUIDs, ordem e paginação preservados.
Detalhes de um membro usam o contrato D02C; thumbnails continuam pelo método existente.
Nenhum caminho da tela chama detector, planner, salva decisão ou executa operações físicas.
A demo SQLite existente não foi modificada, nem seu schema ou migrations.

No modo normal, ambos os métodos retornam `{status:"analysis_not_available"}` para pedidos
válidos, sem consultar catálogo ou mídia. Isso não é vazio completo, falha temporária nem
análise executada. Não há botão de retry/restart para essa capacidade ausente. Sem conexão,
a falha de transporte é `temporarily_unavailable`; erro interno é `internal_error`.

## Contrato efetivo e decisões ratificadas

A ponte autenticada JSON-lines mantém os métodos existentes e acrescenta somente:

| Método Python | Parâmetros |
| --- | --- |
| `duplicates.list` | `{page_size?, after?}` |
| `duplicates.group` | `{snapshot_id, group_key, page_size?, after?}` |

`page_size`: inteiro estrito de 1 a 50, default 24; boolean não é inteiro aceito.
`after`: texto opaco ou null. Parâmetros desconhecidos são rejeitados. O preload expõe
`listDuplicates({pageSize?,after?})` e `getDuplicateGroup({snapshotId,groupKey,pageSize?,after?})`;
o main valida os objetos novamente e traduz somente esses campos. Não recebe modo demo,
catálogo, caminhos nem nomes arbitrários de método. O modo demo é escolha do bootstrap existente.

Resultado discriminado: `{status:"ready",page:...}` ou status fixo `analysis_not_available`,
`invalid_request`, `stale_snapshot`, `not_found`, `response_too_large`, `internal_error` ou
`temporarily_unavailable`. Erros públicos não contêm o pedido, stack, paths ou mensagens privadas.
Falhas inesperadas Python continuam usando o envelope existente `backend_failure`, traduzido
para `internal_error` no IPC de duplicatas.

As páginas incluem `version=1`, `snapshot_id`, `source="synthetic_fixture"`,
`freshness="synthetic"`, `observed_at=null`, cobertura, issues e contadores globais,
`total_count` do conjunto paginado e `next_cursor`. Na lista, `groups` contém resumos; no grupo,
`group` contém o resumo completo e `members` contém a página de ocorrências.

Resumo: `group_key`, `sha256`, `byte_size`, `evidence_fingerprint`, `occurrence_count`,
`physical_copy_count`, `blocks`, `plan_state`, `review`. Membro: IDs de Asset, FileLocation e
LibraryRoot, nome da raiz, relativo, `location_source`, hardlink, conflito, proteção e bloqueios.
Não há device/inode, path absoluto, URL de arquivo ou autorização de operações físicas.
Os enums de domínio são reutilizados; DTOs existentes não foram alterados. Os exports de funções
de análise/revisão passaram a carregar sob demanda em `duplicates/__init__.py`, preservando seus
nomes públicos, para que importar enums não carregue detector ou planner no desktop.

### Snapshot e cursor

Cada processo da bridge cria um UUID de snapshot de sessão; o conteúdo da fixture é determinístico,
o UUID da sessão não. Restart cria outro snapshot. Não há persistência ou importação de resultados.

Cursor: base64url sem padding de JSON canônico ASCII (`sort_keys`, separadores compactos), com
campos exatos `{v:1,snapshot,order,group,offset}`. `group=null` na lista, ou chave do grupo nos
membros. `order="sha256-size/root-name-relative-location-v1"`. Grupos seguem SHA-256/tamanho;
membros seguem nome da raiz, relativo e location ID. Offset é inteiro positivo dentro do conjunto.
Cursores fora do formato, com padding, versão/ordem errada ou grupo cruzado são `invalid_request`;
snapshot de outra sessão é `stale_snapshot`. O cursor não é assinatura nem autorização; os únicos
dados acessíveis já são a projeção sintética da sessão. Tamanho máximo do cursor: 2048 caracteres.

`group_key` é `sha256:tamanho_decimal`, somente chave de apresentação no snapshot, não Asset ID.
Fingerprint permanece null, pois não foi calculada evidência física. Decisão ausente e plano
não conhecido são null; nenhuma ausência vira `ready` ou proteção falsa.

### Inteiros e limites

`byte_size` é sempre string decimal, inclusive para tamanhos pequenos. O grupo grande usa
`"9007199254740993"` para demonstrar precisão acima de `Number.MAX_SAFE_INTEGER`.
Contadores, offsets e versão são números inteiros exatos; a projeção rejeita qualquer número
inteiro fora da faixa segura antes de serializar a página. Nenhum dado é convertido com perda.

Entrada preserva o limite de 64 KiB da bridge. Páginas de duplicatas têm orçamento de 240 KiB
no JSON ASCII compacto; o envelope completo ainda é limitado a 256 KiB por `_write`, incluindo
request ID e newline. Uma resposta excessiva gera `response_too_large`, nunca truncamento de
IDs, relativos ou membros. O supervisor mantém seu limite de 256 KiB e timeouts existentes.
Issues são uma lista global pequena e integral; ultrapassar o orçamento falha explicitamente.
Paginação de issues e orçamento para resultados físicos continuam pendentes antes de D03-02.

## Fixture e proveniência simulada

A projeção lê somente IDs e relativos da demo já criada e bloqueada em `query_only`.
Todos os 73 Assets e todas as 55 FileLocations catalogadas permanecem iguais. Conforme
clarificação explícita do solicitante, ocorrências adicionais existem **somente na projeção**,
com UUIDs determinísticos e `location_source="projection_fixture"`; não são inseridas no SQLite.
As ocorrências originais têm `location_source="catalog_fixture"` e preservam seus IDs e relativos.
Cada linha distingue esses casos; detalhes D02C mostram as localizações realmente catalogadas,
não as ocorrências adicionais da projeção. Nenhum Asset novo é criado.

| Grupo | Cenário sintético |
| --- | --- |
| 1 | Duas ocorrências/cópias independentes; revisão e proteção desconhecidas |
| 2 | Três ocorrências, duas cópias físicas: dois nomes do mesmo Asset simulam hardlinks |
| 3 | Conflito de identidade, revisão histórica stale e motivo com markup literal |
| 4 | 105 membros, múltiplas ocorrências do mesmo Asset, proteção e bloqueio; tamanho decimal grande |

São 112 ocorrências simuladas no total. SHA-256 são constantes simuladas, sem hashing.
Cobertura demo padrão: partial, issue root_offline e bloqueio incomplete_coverage. O contador de
hashing é zero e `observed_at` é null. Não se afirma elegibilidade física dos paths sintéticos.
Casos complete/partial/unavailable, vazios ou não, são exercitados por injeção de read model em
testes, sem opção de cenário controlada pelo renderer. UUIDs derivados aqui identificam apenas
ocorrências simuladas; não redefinem a criação de Asset no domínio.

## UX, lifecycle e acessibilidade

Lista com páginas de dois grupos para tornar o exercício de paginação visível; membros com 24
por página. Contagens físicas e de ocorrências são distintas; não há estimativa de espaço liberado.
Banner de demonstração, cobertura e issues permanecem visíveis. Revisão stale é histórica;
proteção null é desconhecida. Zero grupos só significa ausência no escopo quando a cobertura é
complete; parcial ou indisponível não permite essa conclusão. Textos Unicode, markup e relativos
longos são renderizados como texto React, com quebra de linha, sem interpretação HTML.

Botões nativos, nomes acessíveis, foco visível e estados textuais não dependem de cor.
Abertura do grupo leva foco a Fechar grupo; Escape fecha e restaura o botão de origem.
Detalhes têm prioridade de Escape e retornam foco ao membro. Loading de grupo e paginação são
independentes; refs bloqueiam pedidos repetidos por duplo clique. Respostas antigas são ignoradas
após troca/fechamento de grupo, navegação e troca de geração. Erro de página preserva os itens e
permite repetir a leitura do mesmo cursor. Snapshot stale oferece reabrir lista, sem mesclar páginas.

`onBackendReset` é uma assinatura estreita no preload para a notificação do restart existente;
não expõe ipcRenderer. Após restart bem-sucedido, o main notifica o renderer: a projeção/seleção de
duplicatas é descartada e recarregada. A recuperação D02C da galeria continua preservada.
Isso não é lifecycle de análise física: não foram criados job, worker, HTTP ou progresso de hash.
Sandbox, contextIsolation, ausência de Node no renderer, CSP, bloqueios de navegação e autenticação
foram mantidos. Não há controles de escolha, gravação, revalidação, quarentena ou execução.

## Validação e evidências

Os gates finais foram executados sobre os arquivos desta entrega. Testes usam apenas
catálogos sintéticos em memória/temporários; os smokes usam Electron, preload e Python reais em
KDE Wayland. Screenshots ficam exclusivamente em `/tmp`, fora do Git.

Falhas encontradas durante o trabalho: o cache uv padrão está em filesystem read-only;
`UV_CACHE_DIR=/tmp/playmemories-d03-01-uv-cache` resolve sem mudar configuração/lockfile.
A primeira tentativa gráfica herdou `ELECTRON_RUN_AS_NODE`; os comandos efetivos removem essa
variável com `env -u ELECTRON_RUN_AS_NODE`. Um smoke identificou fechamento indevido de detalhes
da galeria no restart; a correção preserva esse fluxo e invalida apenas a seleção de duplicatas.
Diagnósticos de cor/cache do Chromium e erros esperados ao parar o backend foram observados;
não são tratados como evidência de acesso à mídia ou como testes omitidos.

### Resultados finais

| Verificação | Resultado |
| --- | --- |
| `uv sync --locked` (cache padrão) | FAIL ambiental: filesystem read-only |
| `UV_CACHE_DIR=/tmp/playmemories-d03-01-uv-cache uv sync --locked` | PASS, sem alterar lockfile |
| `uv run pytest` com esse cache | PASS, 317 testes, 10,65 s |
| `uv run ruff check .` com esse cache | PASS |
| `uv run ruff format --check .` com esse cache | PASS, 95 arquivos |
| `git diff --check` e novos arquivos com `git diff --no-index --check /dev/null -- <arquivo>` | PASS |
| `pnpm --dir desktop test` | PASS, 60 testes em 8 arquivos |
| `pnpm --dir desktop lint` | PASS |
| `pnpm --dir desktop typecheck` | PASS |
| `pnpm --dir desktop build` | PASS, também executado pelos smokes |
| `env -u ELECTRON_RUN_AS_NODE UV_CACHE_DIR=/tmp/playmemories-d03-01-uv-cache pnpm --dir desktop smoke:demo` | PASS, KDE Wayland, Electron/preload/Python reais |
| Mesmo ambiente, `pnpm --dir desktop smoke` | PASS, modo normal, sem retry enganoso |

Resultado após ajuste exclusivamente ambiental do cache uv e da variável herdada do Electron:
**PASS**. As tentativas anteriores e a regressão corrigida estão registradas acima.

Smokes verificam paginação da galeria 24/48/72/73 em ordem exata, PNGs sintéticas decodificadas,
quatro grupos, hardlink, revisão stale, 105 membros únicos, detalhes D02C, Escape/foco, restart,
recuperação de falhas e ausência de preload. Redimensionamentos: 1180×760, 860×560, 760×560 e
760×520, sem overflow horizontal. Aviso de privacidade também é conferido na árvore acessível.
A ausência de Node e a lista exata de funções expostas pelo preload são verificadas no smoke.
Testes de contrato adicionais cobrem precisão numérica, orçamento de payload, cursor cruzado,
snapshot obsoleto, páginas vazias e garantia de nenhuma escrita/detecção física.

Evidências visuais locais, não versionadas:

- `/tmp/playmemories-d03-01-duplicates.png`: lista, banner sintético, cobertura e grupo aberto.
- `/tmp/playmemories-d03-01-member-details.png`: detalhes D02C a partir de um membro.
- `/tmp/playmemories-d03-01-normal.png`: capacidade ausente, sem retry.
- `/tmp/playmemories-d03-01-1180x760.png`, `-860x560.png`, `-760x560.png`, `-760x520.png`:
  texto Unicode longo e layout nas dimensões homologadas (mesmo prefixo de filename).

### Arquivos da entrega

| Área | Arquivos |
| --- | --- |
| Projeção Python e ponte | `src/playmemories_photo_manager/desktop/duplicates.py` (novo), `desktop/bridge.py` no mesmo pacote |
| Carregamento de enums sem análise física | `src/playmemories_photo_manager/duplicates/__init__.py` |
| Electron | `desktop/src/main/backend.ts`, `main.ts`, `preload.cts`, `duplicates.ts` (novo) |
| Renderer | `desktop/src/renderer/DuplicatesView.tsx` (novo), `App.tsx`, `types.ts`, `styles.css` |
| Testes e smoke | `tests/test_desktop_duplicates.py` (novo), `desktop/src/main/duplicates.test.ts` (novo), `desktop/src/renderer/duplicates.test.tsx` (novo), `desktop/src/main/smoke.ts` |
| Documentação | `docs/desktop-mvp-d03-01.md` (novo) |

Árvore de trabalho contém somente essas mudanças locais, sem staging/commit, mídia, bancos,
screenshots ou artefatos temporários rastreados. Schema, migrations, lockfiles e o seed original
da demo permanecem sem alterações. Auditoria independente Gemini ainda não executada para D03-01.

## Limites e rastreabilidade J9–J11

J9: detecção backend preexistente continua disponível aos seus casos de uso; esta interface
não a executa. Escopo configurável, hashing físico, progresso e cancelamento desktop ficam para
D03-02, após decisão de lifecycle. J10: backend já persiste escolhas humanas, mas esta UI não
salva revisão nem habilita escrita. J11: backend pode persistir stale ao gerar plano; esta UI
não chama essa função, não gera/exporta plano nem revalida evidência. O planejamento D03-00
continua normativo; jornadas históricas não foram reescritas como se tais capacidades estivessem
entregues no desktop.

A fixture prova apresentação e fronteiras, não throughput, integridade física ou espaço recuperável.
D03-02 exige decisão de execução responsiva, conexão, cancelamento/timeout/shutdown, publicação de
snapshot e paginação de issues. Projeções reais precisam validar validade e proveniência próprias;
não devem reutilizar contagens simuladas, importar JSON operacional do Lab ou habilitar detector
síncrono no handler. Nenhuma atividade no Duplicate Lab ou em mídia pessoal foi necessária.


## Homologação e publicação D03-01

O solicitante comunicou aprovação independente Gemini **PASS**, sem achados BLOCKER, MAJOR
ou MINOR, e autorizou consolidar commits, publicar a branch e abrir PR contra main. O parecer
é registrado conforme essa comunicação; não constitui nova auditoria executada pelo Codex.
O conteúdo anterior descreve a preparação e a entrega para auditoria e foi preservado
integralmente, inclusive falhas observadas, evidências, limitações e riscos residuais.
A referência anterior a auditoria pendente corresponde àquele momento da entrega.

A publicação preserva a implementação homologada: 73 Assets da galeria, quatro grupos
sintéticos, paginação dos 105 membros e distinção de analysis_not_available. Nenhum código
funcional foi alterado nesta consolidação. Resultados dos gates reexecutados após os commits
serão registrados na PR, separados dos resultados históricos acima. Não há nova homologação
de análise física, desempenho ou lifecycle, nem início de D03-02.

O merge não faz parte desta autorização e depende de decisão específica posterior.
