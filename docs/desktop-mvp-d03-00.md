# Desktop MVP D03-00 — checkpoint arquitetural de duplicatas

Data: 2026-10-29. Escopo: auditoria local e proposta documental; D03-01 não iniciado.
Nenhum algoritmo, código funcional, schema ou migration alterado. Nenhuma operação em mídia.

## Base inspecionada e método

Photo Manager: `main`, HEAD `7654f18031511bf63767e858162cfc99491585b5`, baseline solicitada.
Working tree inicialmente limpa, inclusive não rastreados. Remoto `origin`:
`https://github.com/CleberNandi/playmemory-photo-manager.git` (fetch/push).
Duplicate Lab: branch ativa `feat/exact-duplicate-quarantine`, HEAD
`4a93464cb884cce7fbc1b69af5cbd9b0edbe424b`, árvore limpa. Apesar do nome da branch,
esse checkout contém plano/galeria dry-run, não o executor posterior. Remoto `origin`:
`https://github.com/CleberNandi/playmemory-duplicate-lab.git` (fetch/push).
O nome remoto do projeto é **playmemory-duplicate-lab**, não o nome plural do diretório.

Inspeção por `git status`, `branch -avv`, `rev-parse`, `remote -v`, `log --all`,
`worktree list`, `ls-tree` e `show`: sem checkout, fetch, atualização de refs ou escrita no Lab.
Refs remotas são as disponíveis localmente; não se afirma que correspondam ao servidor hoje.
Não foram abertos catálogos operacionais, imagens ou artefatos privados de homologação.

Foram lidos AGENTS.md, GEMINI.md, ADR-001–004, documentação de duplicatas, jornadas e
contratos desktop pertinentes. GEMINI.md orienta revisão independente, não constitui parecer
Gemini desta entrega. `implement-increment` foi consultada e exclui tarefas apenas documentais;
`git-integration` não se aplica. `quality-gates` rege a validação final. A orientação
`postman:api-engineer` foi consultada para reutilizar contratos locais; setup/publicação Postman
ou coleção HTTP não acrescentam evidência à ponte JSON-lines desta tarefa.

### Trabalhos do Lab além da main

| Ref local ou remota disponível | HEAD abreviado | Conteúdo relevante |
| --- | --- | --- |
| `main`, `origin/main`, `perf/exact-size-prefilter` | `96b2144` | Detecção exata com pré-filtro por tamanho |
| `feat/exact-duplicate-quarantine`, `origin/feat/exact-duplicate-review-plan` | `4a93464` | Snapshot, plano, revalidação e galeria offline |
| `feat/exact-reversible-quarantine` | `5a0b12e` | Autorização, executor Linux, journal, retomada/restauração |
| `feat/visual-pair-review` | `16f61d9` | Revisão explícita de pares; local atrás de `origin/feat/visual-pair-review` (`1d42ffe`) |
| `feat/visual-set-review` | `31aa8cc` | Fila visual limitada e registro de aceite Arch |
| `feat/visual-content-candidates` | `6c2dd3a` | Agrupamento binário opcional na fila visual; sem tracking mostrado |
| `feat/visual-queue-pagination` | `53f8bda` | Paginação e registro posterior de aceite Arch |
| `experiment/local-feature-matching` | `b9bf4a1` | ORB/geometria experimental |
| `investigation/orb-mutual-false-positives` | local `96b2144`, remota `096cddb` | Investigação e documentação histórica divergentes |

As branches visuais possuem worktrees próprias. Foram lidas por referência, sem alterar essas
árvores. Não existe uma única “última implementação” representada pela main: há uma sequência de
capacidades em branches e registros de aceite posteriores. Datas de commits não substituem
ancestralidade nem homologação.

## Inventário e matriz de capacidades

“Implementada no produto” significa código e testes disponíveis, não UI entregue.
“Homologada no laboratório” abaixo significa aceite registrado na documentação versionada,
atribuído ao operador e restrito aos conjuntos de estudo; não é reexecução nesta sessão.
“Experimental” inclui implementação sem homologação suficiente para uso no produto.

| Capacidade | Photo Manager | Duplicate Lab | Lacuna para desktop |
| --- | --- | --- | --- |
| Tamanho + SHA-256 integral | Implementada: `duplicates/detector.py` | Implementada na main; fluxo exato homologado no Lab | Nenhum comando desktop de detecção |
| Asset/FileLocation e cópias físicas | Implementada; IDs preservados, `(device,file_id)` distintos | Inventário por paths/identidade física, sem domínio Asset | Adaptar apresentação, não importar identidade do Lab |
| Cobertura e issues | Implementada: complete/partial/unavailable | Exclusões, bloqueios e invalidação de snapshots | Expor cobertura global e escopo |
| Escolha humana/motivo e histórico | Implementada: `duplicates/review.py`, migration 002 | Plano exato homologado | Desktop ainda read-only |
| Proteção e hardlinks | Implementada no plano; conflitos de identidade explícitos | Plano bloqueia hardlinks e dependências conhecidas | UI não pode ocultar bloqueios |
| Retention policy | Inexistente como política automática no produto | `retention.py`: preferência/tie/inconclusive; regra não autoriza ação | Não necessária para D03-01 |
| Plano dry-run/revalidação | Implementada; pode escrever status stale no catálogo | Homologada no Lab | Falta contrato desktop e ciclo de execução |
| Lista/revisão de exatas no desktop | Inexistente | Galeria HTML estática homologada de forma delimitada | D03-01 proposto abaixo |
| Comparação visual humana | Inexistente | Pares e fila limitada homologados; pHash/SSIM/MAE | Fora de D03; similaridade não é igualdade |
| Paginação visual | Inexistente para duplicatas; galeria comum já pagina | Homologada em `53f8bda`, cobertura de IDs conferida pelo operador | Reaproveitar princípio, não HTML/schema |
| Quarentena/journal/restauração | Inexistente | Homologada em cópias de estudo no Linux; implementação `5a0b12e` | Sem coordenação com catálogo do produto |
| ORB/identidade de captura | Inexistente | Experimental; falsos positivos documentados | Não incorporar nem ajustar algoritmo |
| Job com progresso/cancelamento de detecção | Inexistente | Fluxos CLI não oferecem contrato desktop equivalente | Decisão de lifecycle anterior à análise real |
| Snapshot persistido completo de detecção no produto | Inexistente | Snapshot JSON no Lab | Decisões salvas não substituem resultados completos |

### Contratos existentes do produto

Fontes: [detector](../src/playmemories_photo_manager/duplicates/detector.py),
[DTOs/enums](../src/playmemories_photo_manager/duplicates/models.py),
[revisão](../src/playmemories_photo_manager/duplicates/review.py),
[migration 002](../src/playmemories_photo_manager/catalog/migrations/002_exact_duplicate_review.sql)
e [contrato publicado](exact-duplicates.md).

- `find_exact_duplicates(connection)` lê todas as localizações catalogadas. Não recebe seleção
  de raízes/pastas/extensões. Só considera file/present em raiz available. Pré-observa tamanho,
  faz hash para tamanhos repetidos, não persiste hash nem cria/funde Assets. Retorna
  `ExactDuplicateResult(coverage, groups, issues, eligible_location_count, hashed_location_count)`.
- `ExactDuplicateGroup` contém sha256, byte_size, members e physical_copy_count. Cada
  `DuplicateMember` traz Asset, localização, raiz, relativo, tamanho/hash, device/file_id/link_count.
  Hardlinks continuam membros; contagem física não soma nomes para o mesmo inode.
- `DuplicateCoverage`: complete, partial, unavailable. `DuplicateIssueKind`: root_offline,
  location_unavailable, symlink_blocked, invalid_path, not_regular_file, file_changed,
  read_failed, confinement_unavailable. Qualquer issue torna o resultado partial; ausência de
  confinamento suportado produz unavailable. Isso não é uma varredura de arquivos não catalogados.
- `save_exact_duplicate_decision` redetecta, exige keep no grupo e motivo não vazio; transação
  `BEGIN IMMEDIATE` salva UUID da decisão, snapshot dos membros e fingerprint canônico; decisão
  anterior current do mesmo hash/tamanho passa a stale. Não remove histórico nem arquivos.
- Migration 002 usa tabelas STRICT, FKs RESTRICT e índice único parcial para uma decisão current
  por hash/tamanho. Salva created_at/stale_at; não salva resultado global, cobertura ou job.
  DTO `ExactDuplicateDecision` não expõe esses timestamps.
- `generate_exact_duplicate_plan` redetecta e compara evidências. Retorna pending/ready/blocked/stale;
  pode persistir stale em transação. Portanto é consultivo em relação a originais, **não** uma
  consulta sem escrita SQLite. Não deve entrar diretamente na bridge query-only.
- Blocos: incomplete_coverage, hardlink, identity_conflict, protected,
  preserved_copy_unverified. Cobertura parcial global bloqueia até grupos verificáveis.
  Grupo sem decisão fica pending mesmo contendo blocks; estado não substitui lista de bloqueios.
- Proteção atual é presença de álbum, tag, anotação, metadata ou thumbnail catalogada.
  Candidato protegido bloqueia o plano; keep protegido não implica sozinho esse bloqueio.
  `candidate=true` é teórico e pode coexistir com protected. No grupo stale, membros são
  históricos e `protected=False` é preenchimento do modelo, não prova atual de desproteção.
- Fingerprint inclui IDs, relativo, hash, tamanho e identidade física/link count, na ordem
  determinística dos membros. Não é Asset ID, assinatura, autorização ou observação em tempo real;
  não inclui mtime/ctime, nome de exibição da raiz nem dependências do catálogo.
- `action_authorized` e `operations_performed` são False. Nenhum executor existe no produto.

### Segurança e limites da evidência

POSIX: raiz absoluta aberta componente a componente, descritores relativos, `O_NOFOLLOW`,
arquivo regular, comparação de device/inode/size/mtime/ctime/nlink antes/depois do hash e
revalidação do nome contra descritor. Observações catalogadas de tamanho/mtime/filesystem_id e
hash verified são confrontadas quando presentes. Symlink, traversal e path não canônico falham
fechados. Ausência dessas primitivas não habilita fallback menos seguro.
Isso detecta alterações observáveis; não cria snapshot atômico contra qualquer escritor.
Leitura pode atualizar atime. Não equiparar offline, missing e observação física atual.

## Integração desktop e decisões D03

[Bridge Python](../src/playmemories_photo_manager/desktop/bridge.py), supervisor
`desktop/src/main/backend.ts`, preload e main implementam JSON-lines autenticado por token de
sessão, allowlists e correlação por request ID. Métodos atuais: gallery.list, thumbnail.get,
asset.details e shutdown. Catálogo externo abre mode=ro/query_only, exige schema v2; demo usa
SQLite em memória e dados sintéticos. O shell normal atual inicia sem selecionar catálogo.
Renderer sem Node, com sandbox/contextIsolation, sem acesso direto ao SQLite ou filesystem.

Supervisor: startup 10 s, request 5 s, shutdown 1,5 s e escalada de kill 2 s; limite de buffer
256 KiB, entrada Python 64 KiB. Python despacha sequencialmente. Timeout remove a promessa,
mas **não cancela o trabalho Python**; restart/encerramento pode terminar o processo.
Um hash longo no despacho impediria galeria, detalhes e shutdown. Aumentar timeout não resolve
progresso, cancelamento ou isolamento de conexões. D03-01 não chamará detector nem gerador de plano
em handler síncrono. Qualquer worker futuro exige decisão específica conforme ADR-004.

Decisões deste checkpoint, sem exceção às ADRs:

1. Reutilizar módulos do produto. Lab é fonte seletiva de evidência, nunca serviço executado pelo
   produto, schema compartilhado ou dependência perceptual/transitiva importada por padrão.
2. Preservar UUID lógico imutável, ocorrências FileLocation e SHA-256 como evidência binária.
   Hardlinks não são cópias independentes; nenhuma fusão/exclusão/escolha automática.
3. Começar pela apresentação read-only em **fixture sintética**, explicitamente demo. Não introduzir
   persistência de snapshot nem ler decisões como se fossem inventário atual de todos os grupos.
4. Não importar JSON operacional do Lab. Snapshot de evidências real fica para etapa própria com
   origem, limites, validade, escopo e lifecycle definidos. Dados salvos de revisão podem futuramente
   aparecer como históricos, sem certificar existência física atual.
5. Originais e sidecars permanecem fora de qualquer mutação D03-01–04. Quarentena exigirá outra
   decisão explícita e protocolo coordenado entre filesystem, journal e catálogo; não é D03-04.

## Proposta de contrato mínimo D03-01 (ainda não implementado)

Uma projeção de apresentação própria é necessária: DTOs existentes não trazem root display name,
origem/validade do resultado ou paginação, e o plano não traz physical_copy_count. Reutilizar enums
existentes quando a semântica coincidir. Evitar serializar dataclasses internas indiscriminadamente.

Proposta de métodos estreitos: `duplicates.list` com `{page_size, after}` e
`duplicates.group` com `{snapshot_id, group_key, page_size, after}` para membros. Preload expõe
funções específicas, não método arbitrário. D03-01 atende apenas demo; modo normal responde
unavailable com motivo fixo `analysis_not_available`, sem abrir mídia nem simular análise real.
Valores iniciais propostos: páginas de 1..50 grupos/membros, default 24; limite de mensagem
preservado. Se excedido por strings, erro sanitizado explícito; nunca truncar paths/IDs silenciosamente.
Cursor opaco vinculado a versão, snapshot, ordenação e grupo; cursor inválido é erro,
snapshot substituído produz stale. Ordem determinística hash/tamanho e raiz/relativo/location_id.

| Campo da projeção | Semântica proposta |
| --- | --- |
| version, snapshot_id, source | Versão 1; ID opaco da sessão; source=synthetic_fixture em D03-01 |
| observed_at, freshness | Timestamp da evidência quando existente, null na fixture; synthetic/snapshot/stale; nunca “atual” inferido |
| coverage, issues, eligible_location_count, hashed_location_count | Semântica do resultado original, sempre referente ao snapshot completo, não à página |
| group_key | Par canônico SHA-256 + tamanho, chave de apresentação dentro do snapshot; não UUID lógico |
| evidence_fingerprint | Fingerprint do conjunto completo ordenado quando disponível; null se não conhecido; não recalculado por página |
| sha256, byte_size | Igualdade confirmada por hash integral na origem da evidência; na demo valores são explicitamente simulados |
| occurrence_count, physical_copy_count | Total de FileLocations e identidades físicas distintas no conjunto observado; nunca espaço recuperável garantido |
| asset_id, location_id, library_root_id | UUIDs preservados, cada localização permanece visível |
| root_display_name, relative_path | Nome da raiz e path relativo como texto; sem root absoluto, URL file ou acesso a arquivo |
| hardlinked, identity_conflict | Flags da evidência; não expor device/inode para navegação do renderer |
| protected, blocks | protected boolean ou null quando desconhecido/histórico; blocks preserva enums do produto |
| review | null se desconhecida; senão decision_id, status current/stale, keep_location_id e reason históricos |
| plan_state | pending/ready/blocked/stale somente quando conhecido, senão null; não calcular ready por ausência de decisão |
| next_cursor, total_count | Continuidade e total do conjunto/grupo; membros paginados não equivalem a grupo completo |

Issues precisam de paginação própria ou resposta limitada com total/continuação explícitos antes
de conectar resultados reais; D03-01 usa fixture com issues dentro do orçamento. Não descarregar
milhares de membros/issues numa única resposta. Não calcular fingerprint ou contagem física apenas
com a página carregada. Campos numéricos potencialmente acima de Number.MAX_SAFE_INTEGER
(tamanho/contadores futuros) precisam de serialização decimal exata ou validação de faixa no
contrato final; timestamps ns e identidade POSIX não entram neste DTO mínimo.

A lista mostra resumo; abertura do grupo permite alcançar todos os membros e acessar detalhes
read-only do Asset pelo contrato D02C. Esse painel pode truncar suas localizações em 100 com
locations_truncated; não substitui a paginação completa dos membros do grupo. Thumbnail/fallback
é apresentação, não condição para igualdade. Sem botões salvar escolha, revalidar ou executar.
A fixture existente de 73 Assets não contém grupos exatos físicos: não executar detector contra
seus paths sintéticos. Acrescentar projeção demo isolada com IDs coerentes, preservando paginação
existente; não inventar metadata ou hashes verificados de mídia real.

### Estados visuais e de transporte

| Estado | Comportamento |
| --- | --- |
| Vazio | Só “nenhum grupo no escopo analisado” quando coverage complete; demo claramente rotulada |
| Loading | Carregamento da projeção/página; não anuncia hashing nem progresso fictício |
| Erro | invalid_request/internal_error sanitizados; mantém contexto e permite tentativa pertinente |
| Parcial | Mostra grupos e issues/contagens; zero grupos não significa ausência de duplicatas |
| Desatualizado | Snapshot/grupo ou revisão histórica identificados; não apresenta keep como revalidado nem protected=false como fato atual |
| Indisponível | Backend parado, timeout/busy ou análise não disponível; distinguir motivo recuperável de capacidade ausente |

Esses estados são ortogonais: parcial pode ter grupos, decisão stale ou falha de página seguinte.
Troca de grupo, fechamento e restart invalidam respostas antigas por geração/snapshot, preservam
seleção coerente e não misturam páginas. Retry da leitura não inicia scan. Foco, teclado, Escape,
textos acessíveis e preservação da galeria seguem D02C.

## Rastreabilidade das jornadas e descrições históricas

[As jornadas](mvp-user-journeys.md) são intenção de produto; sua legenda e capacidades estão
historicamente anteriores ao desktop atual. Propostas fundamentadas, sem editar esse arquivo aqui:

| Jornada | Descrição desatualizada / diferença | Atualização recomendada |
| --- | --- | --- |
| J9 | “inexistente no produto” | Detecção backend implementada em 01A, tamanho/SHA-256/diagnósticos testados; seleção de escopo, job, progresso, cancelamento e UI ainda ausentes |
| J10 | “integração inexistente”, só modelos/handoff | 01B registra keep/motivo e histórico com IDs; falta revisão desktop. Não prometer estimativa de bytes recuperáveis para hardlinks nem dependências externas detectadas |
| J11 | “inexistente no produto”; artefato e revalidação imutável | Plano backend 01B implementado; objeto retornado não é artefato exportado versionado do Lab. Revalidação pode escrever stale no catálogo, sem alterar snapshot histórico; UI/exportação ainda ausentes |

J9 descreve extensões e seleção configuráveis que a função do produto não recebe. J10 menciona
dependências em sentido amplo: produto protege relações catalogadas, não resolve sidecars/catalogação
externa como o operador do Lab. J11 menciona destinos e checksum de artefato: produto não propõe
destino de quarentena nem exporta plano selado. Não transportar essas promessas para D03-01.

Outras evidências históricas: docs D02C registra “sem merge” no contexto de sua publicação;
a baseline atual já contém a entrega. A seção “fora de escopo” de exact-duplicates.md refere-se
à interface de duplicatas, não à inexistência de todo desktop. No Lab, o checkout `4a93464`
ainda lista quarentena pendente; handoffs posteriores registram implementação/homologação.
O resumo de paginação ainda contém pendência Arch, mas o final de visual-set-review.md em
`53f8bda` registra sua conclusão. Preferir registro específico posterior, atribuindo a origem.
Não reescrever histórico como se testes antigos tivessem sido executados hoje.

## Estratégia de testes sintéticos

Base reutilizável: `tests/conftest.py` (SQLite temporário), helpers de
`test_exact_duplicates.py` e `test_exact_duplicate_review.py` (bytes em tmp_path),
`desktop/demo.py` (73 Assets determinísticos em memória, query-only e PNGs geradas),
testes de bridge/detalhes/thumbnails e testes do supervisor/renderer. Testes atuais cobrem
pré-filtro, conteúdo distinto de mesmo tamanho, hardlinks, symlinks/ancestrais, traversal,
mutação durante hash, leitura falha, plataforma sem confinamento, proteção, stale e histórico.

Para D03-01, testar comportamento de apresentação e fronteira, sem novo algoritmo:

- Duas cópias independentes, hardlinks e múltiplas localizações do mesmo Asset: IDs intactos,
  occurrence_count distinto de physical_copy_count, todos os membros alcançáveis por paginação.
- Vazio completo, parcial vazio/com grupos, indisponível, erro, revisão desconhecida/stale,
  proteção desconhecida, conflito e grupo grande; nenhuma ausência vira afirmação de segurança.
- Contrato estrito, cursor cruzado/obsoleto, limite de payload e precisão numérica; nomes Unicode,
  caminhos relativos e motivo com markup renderizados como texto; sem paths absolutos em erros.
- Bridge sob query_only, sem escrita, sem chamada ao detector/planner, sem abertura de mídia;
  renderer não habilita demo por parâmetro e não fornece caminhos ao backend.
- Troca rápida, resposta tardia, restart, paginação preservada, foco/teclado e thumbnail ausente;
  modo normal indisponível e modo demo explícito. Smoke futuro só com fixture.

Não versionar bancos, JSONs operacionais, fotografias, screenshots ou outros artefatos gerados.
Fixtures read-model não demonstram throughput de hashing; testes reais de lifecycle virão antes
de disponibilizar análise real. Não executar os exemplos físicos de quarentena do Lab aqui.

## Riscos e decisões necessárias antes da implementação correspondente

- Desempenho: leitura integral repetida na detecção, save e geração de plano; stat de localizações
  e descritores de raízes; memória proporcional aos resultados; nenhuma estimativa de tempo real
  obtida neste checkpoint. Paginação da UI não torna hashing incremental nem limitado em memória.
- Concorrência: snapshot SQL não congela filesystem. Detecção e consulta de proteções/decisões não
  são uma única transação atômica com arquivos. Review pode mudar após exibição. SQLite conexão
  não deve ser compartilhada ingenuamente entre threads; política de escritor e busy precisa ser
  explícita antes de salvar/revalidar via desktop.
- Lifecycle: antes de D03-02 decidir execução cooperativa ou worker justificado, propriedade da
  conexão, uma análise por biblioteca/escopo, ID de job, fases, contadores mensuráveis, cancelamento,
  timeout, encerramento e recuperação. Cancelamento não conclui cobertura; resultado incompleto
  conserva esse fato. Definir publicação/substituição do snapshot e descarte de respostas tardias.
- Segurança: manter confinamento POSIX e erro sanitizado; sem fallback Windows que siga links.
  Não converter relativo em file URL, abrir caminhos enviados pela UI ou importar plano do Lab.
  Nomes/motivos são dados não confiáveis. Espaço “redundante” não é promessa de liberação física.
- Antes de D03-01: ratificar nomes finais, formato de cursor, política numérica e orçamento de
  resposta nos testes de contrato; manter escopo demo/read-only descrito aqui. Se for exigida
  listagem de biblioteca real já em D03-01, replanejar: não substituir fixture por hash síncrono.
- Antes de D03-03: escolher como habilitar escrita de decisões sem enfraquecer a bridge query-only,
  autorização humana e conexão de escrita controlada; não tornar todas as consultas graváveis.
- Antes de D03-04: definir se plano é somente projeção de sessão ou artefato exportável versionado;
  revalidação e escrita stale devem ser comandos explícitos, não efeitos de renderização.
- Futuro físico: autorização vinculada ao plano, dependências/sidecars, coordenação journal-catálogo,
  recuperação e plataformas exigem decisão própria. Homologação do Lab não resolve esses pontos.

## Sequenciamento e critérios de aceite

| Incremento proposto | Entrega delimitada | Condição de saída |
| --- | --- | --- |
| D03-01 | Lista/grupo read-only, fixture sintética e contratos estreitos na ponte existente | Estados e paginação corretos; IDs preservados; zero leitura de originais/escrita; normal indisponível explícito |
| D03-02 | Análise real read-only com lifecycle e snapshot de sessão definidos previamente | UI responsiva; progresso verdadeiro; cancelamento/timeout/shutdown testados; parcial/stale explícitos; POSIX fail-closed |
| D03-03 | Escolha humana e motivo persistidos pelo caso de uso existente | Histórico e transação preservados; revalidação fora do handler bloqueante; bloqueios não removidos pela escolha |
| D03-04 | Apresentação de plano consultivo e comando explícito de revalidação | pending/ready/blocked/stale corretos; escrita stale declarada/controlada; flags False; nenhuma ação física |

Aceite D03-00: inventário rastreável a código/testes e refs, distinção de homologação relatada e
execução atual, lacunas reais de persistência/desktop/lifecycle, escolha de fonte D03-01 e fronteiras
preservadas. Entrega restrita a este documento, sem iniciar implementação nem mudar estado do Lab.
A recomendação objetiva é iniciar D03-01 como apresentação demo read-only; não incorporar mais
algoritmos do Lab nem habilitar detecção física pelo IPC atual.

## Validação desta entrega

Resultados da execução atual são registrados abaixo após os gates. Testes do Lab, operações
físicas, benchmark e smoke gráfico não fazem parte deste checkpoint documental. Nenhuma
homologação nova dessas capacidades é declarada.

| Gate executado em 2026-10-29 | Resultado |
| --- | --- |
| `uv sync --locked` com cache padrão | Falhou: cache padrão em filesystem read-only |
| `UV_CACHE_DIR=/tmp/playmemories-d03-uv-cache uv sync --locked` | PASS, lockfile preservado |
| `UV_CACHE_DIR=/tmp/playmemories-d03-uv-cache uv run pytest` | PASS, 291 testes em 9,30 s |
| `UV_CACHE_DIR=/tmp/playmemories-d03-uv-cache uv run ruff check .` | PASS |
| `UV_CACHE_DIR=/tmp/playmemories-d03-uv-cache uv run ruff format --check .` | PASS, 92 arquivos |
| `git diff --check` | PASS |
| `git diff --no-index --check /dev/null -- docs/desktop-mvp-d03-00.md` | PASS, sem mensagens de whitespace; exit 1 esperado para arquivo novo |

Resultado dos gates após ajustar somente o cache: **PASS**. A primeira falha ambiental está
registrada, sem alteração de configuração do projeto. Verificação de escopo: único arquivo novo
é este Markdown; sem código, migrations, mídia, bancos ou artefatos gerados no diff. Lab permaneceu
limpo, na mesma branch e HEAD. Testes desktop JS/build/smoke: **NOT RUN**, pois não houve alteração
funcional nem de UI; resultados históricos de D02C não são apresentados como execução atual.
Sem commit, push, merge ou mudança de remoto.


## Homologação e publicação do checkpoint

Em 2026-10-29, o solicitante informou a homologação pela auditoria independente Gemini:
**PASS**, sem achados BLOCKER, MAJOR ou MINOR. Esse parecer é registrado conforme a
comunicação do solicitante; não representa nova auditoria executada nesta publicação.
O conteúdo recebido foi preservado integralmente acima desta seção; seu SHA-256 é
`20814578c38178b2e3892883fd3bdce5c97c8c06aa6312094974ed6c1369b167`.

O checkpoint homologado constitui a referência normativa de planejamento D03, subordinada
às ADRs aceitas. Os contratos D03-01 propostos continuam sujeitos à ratificação indicada
neste documento; a homologação não inicia sua implementação nem autoriza operações físicas.
O registro de validação anterior descreve a preparação documental. Commit, publicação e PR
foram autorizados posteriormente; os gates desta publicação serão relatados na PR.
O merge em main depende de autorização específica posterior.
