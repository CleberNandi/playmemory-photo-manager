# Desktop MVP D04-02A — Preparação segura de catalogação

Data: 2026-10-30. **Contrato proposto revisado; implementação ainda não iniciada.**
Base remota confirmada: `main` em `337f8cd266bca19a591482a56aa41ad8a150a074`,
após integração fast-forward da PR #11, homologada pelo Gemini com PASS. O registro da PR
preserva os gates e as limitações manuais de D04-01B. Este documento não altera D04-00 ou ADRs.

## Objetivo e diagnóstico

Preparar uma proposta privada de catalogação de uma pasta explicitamente selecionada,
sem criar Assets ou FileLocations. D04-02B fará revisão humana, autorização e aplicação.
Referências normativas: [D04-00, §§6–8 e observação 02](desktop-mvp-d04-00.md),
[lifecycle proposto D03-02A](desktop-mvp-d03-02a.md) e ADR-001–004 em `docs/adr/`.

Inspeção confirma que o controlador/worker de D03-02A é contrato documental, não código
reutilizável existente. O scanner atual materializa entradas; `prepare_ingestion` usa snapshot
sem orçamento e a bridge despacha sequencialmente. Não habilitar essa chamada diretamente na UI.
O aplicador atual exige plano integralmente aplicável; filtrar a lista visual não resolve o
bloqueio de diretórios. Não relaxar `_require_applicable_plan` globalmente.

## Ordem de implementação e critérios de conclusão

1. **Coleta limitada e snapshot consistente.** Introduzir limites opcionais no scanner,
   preservando comportamento dos chamadores atuais. Contar entradas antes de acumular/ordenar,
   incluindo diretórios e excluídos; interromper no excesso, sem declarar cobertura completa.
   Consultar snapshot limitado dentro de uma leitura consistente, encerrada antes de ler mídia;
   preservar o digest lógico `read_version`, sem anunciá-lo como revisão transacional.
2. **Elegibilidade e recorte explícito.** Manter ScanResult, cobertura e diagnósticos originais.
   Produzir registro privado por candidato com ID opaco, classificação, motivo fixo, versão do
   perfil e evidências de abertura. Somente arquivo regular novo e JPEG aceito pode ser elegível.
   Diretórios cobertos e formatos excluídos recebem justificativa explícita; inconclusão de
   cobertura, conflito ou evidência física nunca pode ser descartada como simples exclusão.
   Usar o contrato tipado do recorte e sua recomputação definidos abaixo antes de integrar a UI;
   não fabricar um plano READY por remoção de warnings ou edição do ScanResult.
3. **Worker e controlador Python.** Implementar o lifecycle de preparação específico com spawn
   de entry point fixo, sem shell e sem herdar SQLite ou descritores de mídia. Conexões abertas
   e fechadas pelo proprietário; canais/filas limitados, controle independente de progresso,
   um escritor de stdout. Uma operação por biblioteca; cancelamento cooperativo, terminação e
   reap obrigatório antes de liberar o slot. Nenhuma importação do detector de duplicatas.
4. **Seleção e grant.** Main abre diálogo de uma pasta e confirmação que explica recursividade,
   leitura e registro de configuração. Python valida raiz/ancestrais por descritores, identidade,
   sobreposição com raízes e destinos do catálogo. Só então registra/reutiliza LibraryRoot em
   comando curto. Grant privado vincula sessão, janela, identidade e escopo, vale cinco minutos
   para admissão e é consumido uma vez. Cancelar diálogo não registra nada; cancelar preparação
   pode deixar a raiz vazia. Troca/fechamento revogam grant e aguardam reap.
5. **IPC e UI.** Propor rotas próprias `ingestion.prepare/status/cancel/page`, sem paths ou MIME
   aceitos do renderer, mantendo validação de sender, sessão, geração e aridade de D04-01B.
   Publicar páginas só depois de validar resultado completo e reap. Progresso com fase/contagens
   reais e total null quando desconhecido. Preparação parcial/cancelada/limitada conserva apenas
   resumo limitado e não permite acessar proposta aplicável. Nenhuma rota de aplicação nesta fase.

## Orçamentos iniciais a medir antes da habilitação

| Recurso | Limite proposto / tratamento |
| --- | --- |
| Entradas observadas | 2.000; a entrada 2.001 encerra por resource_limit |
| Profundidade | 32; exceder bloqueia a proposta inteira |
| Proposta canônica privada | 8 MiB, incluindo evidências/diagnósticos; limitar durante construção |
| Snapshot catalogado | Até 2.000 localizações e 8 MiB; limite inclui consulta/materialização |
| Worker | 30 s, RSS 256 MiB; monitor Linux obrigatório, medir intervalo e overshoot |
| Página pública | Até 50 itens, dentro do envelope de resposta de 256 KiB da bridge |
| JPEG | Até 64 MiB, 40 milhões de pixels, 16.384 por eixo; sem decomprimir pixels |

O perfil abaixo fixa um subconjunto baseline deliberadamente restrito, sem dependência nova.
Progressivo não será declarado malformado: recebe unsupported_jpeg_frame neste perfil inicial.
O fluxo real continua desabilitado até implementação, corpus e auditoria aprovados. Não inferir
EXIF, captura, hash, thumbnail ou preview. Aceite estrutural não comprova decodificação integral.

## Contrato de recorte v1 — MAJOR-01

Em `catalog_ingestion`, adicionar função pura
`scope_catalogable_proposal(original: IngestionProposal, eligibilities: tuple[MediaEligibility, ...])
-> ScopedIngestionProposal`. O tipo novo contém original intacto, elegibilidades, exclusões,
referências elegíveis e scope_fingerprint. Não contém um CatalogChangePlan artificial READY.
`plan_changes`, `authorize_ingestion`, `apply_ingestion`, `_require_applicable_plan` e a semântica
legada de `_proposal_error` permanecem estritos para os chamadores atuais.

Admissão do recorte, em ordem:

1. Recomputar evaluate(original.scan_result) e plan_changes(assessment, snapshot, context),
   exigindo igualdade exata. Validar referências conhecidas, run/root/scope, inclusive as checagens
   físicas/lógicas de `_proposal_error` anteriores à chamada de `_require_applicable_plan`.
   Fatorar essas checagens em helper privado compartilhado, mantendo a chamada estrita legada.
2. Exigir StructuralValidation.VALID, COMPLETE_RECURSIVE_SCOPE, status COMPLETE, confinamento
   descriptor_relative POSIX, raiz física presente e escopo `.` recursivo sem seguir links.
   Impedimentos aceitos somente ENUMERATION_NOT_ATOMIC, CONTENT_NOT_VERIFIED e
   LOGICAL_IDENTITY_UNCONFIRMED, como limitações declaradas; qualquer outro bloqueia.
3. Recusar plano BLOCKED, qualquer change BLOCKED e qualquer diagnóstico ERROR. Warnings globais
   só ROOT_IDENTITY_UNAVAILABLE, com revisão explícita da identidade atual na seleção de raiz;
   não inferir identidade anterior pelo estado persistido available.
4. Exigir uma elegibilidade por entrada, sem duplicatas, omissões ou paths adicionais, vinculada
   à observação exata e à versão do perfil. Para INCONCLUSIVE, admitir apenas diagnóstico único
   NON_FILE_OBSERVATION: DIRECTORY presente em covered_directories ou SYMLINK/REPARSE_POINT/OTHER
   observado sem seguir/abrir seu conteúdo e classificado not_regular_file. Qualquer outro
   diagnóstico, inclusive INCONCLUSIVE_EVIDENCE/PHYSICAL_IDENTITY_UNAVAILABLE, bloqueia tudo.
5. Arquivo NEW_FILE_CANDIDATE só entra nas referências elegíveis se eligible_jpeg. Formato
   excluído fica no manifesto de exclusões. Falha física/read_failed invalida a preparação;
   não converter desaparecimento, conflito ou permissão negada em exclusão por formato.
   KNOWN_LOCATION_OBSERVED permanece conhecido, sem autorização para nova criação. Diretórios,
   links e outros tipos nunca recebem CandidateSelection.

MediaEligibility privado: candidate_id UUID, CandidateReference(run_id, root_id, relative_path),
EntryObservation original, state (eligible/excluded/failed), reason fixo, detected_format
(jpeg/null), profile=jpeg_structural_v1, decoding=not_checked e fingerprint físico da abertura
(raiz/device/inode/size/mtime_ns/ctime_ns antes/depois). Diretórios/formatos nominais não lidos
não inventam fingerprint de conteúdo. IDs opacos e mapa de IDs permanecem privados à operação;
o fingerprint cobre original, classificação, exclusões e IDs em ordem canônica, não só paths.

Em D04-02B, novas APIs `authorize_scoped_ingestion(scoped, candidate_ids)` e
`apply_scoped_ingestion(catalog, scoped, authorization)` recompõem o recorte, nunca aceitam MIME,
kind ou elegibilidade do renderer e vinculam consentimento ao scope_fingerprint e IDs exatos.
A aplicação recompõe snapshot/plano/recorte sob o mesmo BEGIN IMMEDIATE que contém as criações,
após preflight físico fora da transação. Compartilhar o núcleo transacional, não chamar o
aplicador legado com proposta filtrada. Todo conflito bloqueia o lote; PHOTO/image/jpeg vem do
backend. D04-02A implementa/testa recorte, não essas rotas de escrita futuras.

## Coleta e snapshot limitados — MAJOR-03/04

Adicionar ScanLimits opcional e ScanResourceLimitError(reason, observed_count, depth), separados
de ScanStatus. Chamadores sem limites conservam o comportamento atual. No modo limitado, cada
nome enumerado consome uma vez o orçamento global, mesmo se stat falhar. Antes de sort local,
coletar no máximo remaining+1 DirEntries; a sentinela excedente lança a exceção sem stat/leitura
do arquivo e sem publicar ScanResult parcial. Limite também vale no fallback path-based; ele
continua proibido na preparação desktop. Não usar len(list(scandir(...))) nem sorted(iterator).

Raiz `.` tem profundidade 0; entrada tem len(PurePosixPath(relative_path).parts). Entrada de
profundidade 33 dispara resource_limit. Diretório no nível 32 deve ser enumerado para demonstrar
que está vazio; se contiver qualquer entrada, a profundidade excede. Não omitir silenciosamente
seus descendentes. Qualquer estouro é job failed/resource_limit e descarta a proposta completa;
cancel solicitado primeiro pelo controlador prevalece como cancelled. Resumo limitado não vira
ScanResult COMPLETE/PARTIAL inventado. Scanner não passa a usar FAILED com observações.

Worker abre catálogo por adapter read-only com a mesma reserva/validação de inode e header de
D04-01A, sem a conexão rw usada na ativação da sessão. BEGIN explícito; lê raiz e localizações
em ordem estável, páginas até 100, coletando no máximo 2.001 linhas para detectar excesso antes
de materializar mais. Acima de 2.000, aborta; busca Assets únicos na mesma transação, em lotes
limitados. Configurar SQLITE_LIMIT_LENGTH em 8 MiB nessa conexão para impedir uma célula/linha
arbitrariamente grande antes da contagem Python; SQLITE_TOOBIG vira resource_limit, não corrupt.
Contabilizar durante a coleta a representação canônica integral de root/assets/
locations/evidências, máximo 8 MiB, incluindo strings antes de grandes cópias/serialização.
O limite da proposta final inclui também scan, assessment, plano, elegibilidades e exclusões.

Encerrar leitura por rollback e fechar conexão na thread proprietária, inclusive erro/cancel.
Só depois iniciar scan e leitura JPEG. Adicionar `prepare_from_snapshot(snapshot, scan_result,
context) -> IngestionProposal` puro; preservar prepare_ingestion legado. read_version mantém
campos e digest lógico atuais; scope `.` inclui todas as localizações da raiz. Snapshot não é
promessa de atualidade futura: D04-02B revalida no commit. Não manter transação durante mídia.

## Perfil jpeg_structural_v1 — MAJOR-02

Referência consultada: [ITU-T T.81 / ISO 10918-1, Anexo B e C](https://www.w3.org/Graphics/JPEG/itu-t81.pdf).
As restrições seguintes são política do produto, não suporte integral ao padrão. Apenas SOF0,
8 bits, 1 ou 3 componentes, uma scan contendo todos os componentes, sem restart. SOF1/SOF2,
CMYK, arithmetic, lossless, DNL e múltiplas scans ficam excluídos como perfil não suportado.
Essa redução evita afirmar validação progressiva sem máquina de estados/corpus correspondentes.

Verificador abre a partir da raiz e pais retidos por dirfd, O_NOFOLLOW e O_DIRECTORY nos pais;
arquivo O_RDONLY|O_NOFOLLOW|O_NONBLOCK, S_ISREG, sem cruzar device ou mount não autorizado.
Conferir identidade/tamanho/mtime/ctime contra observação antes e após leitura e revalidar raiz
e cadeia de nomes. Mudança => failed/entry_changed_during_verification, não exclusão lexical.
Sem extensão .jpg/.jpeg (case-insensitive), excluir sem ler conteúdo; arquivo vazio ou >
67.108.864 bytes excluído antes de parse. Leitura sequencial em chunks <=64 KiB, nunca read()
sem tamanho. Deadline por arquivo 1 s monotônico e por job 30 s; checar entre chunks/segmentos.
Monitor externo termina worker em I/O bloqueante, sem promessa de interromper syscall de kernel.

Regras de parse, sem descompressão de coeficientes/pixels:

1. SOI FF D8 no offset 0. Fora de entropy, marcador com FF, até 64 FF de fill; FF00 inválido.
   Só admitir APP0..APP15, COM, DQT, DHT, SOF0, SOS e EOI. SOI repetido, RST/TEM fora de scan e
   marcador desconhecido falham fechado. DRI e demais perfis conhecidos são unsupported_jpeg_frame.
2. Todo segmento com comprimento usa big-endian >=2, payload length-2 dentro do arquivo. APP/COM
   são opacos, não interpretar EXIF/ICC. Máximo 256 segmentos com comprimento e 4 MiB totais
   desses segmentos (incluindo comprimentos/markers); exceder => segment_limit_exceeded.
3. SOF0 único, length=8+3*N, P=8, N em {1,3}; dimensões 1..16.384 e produto <=40.000.000.
   IDs de componentes únicos, fatores H/V em 1..4, soma H*V <=10; grayscale H=V=1 neste perfil.
   Seletores DQT em 0..3. SOF antes de SOS, sem frame novo após o primeiro.
4. DQT contém uma ou mais tabelas exatas de 64 valores de 8 bits não zero, ID 0..3; rejeitar
   precision diferente de 0, bytes sobrando e duplicata de ID neste perfil. DHT contém tabelas
   DC/AC, destinos 0..1, 16 contagens seguidas exatamente pela soma dos símbolos (1..256).
   Validar árvore canônica não sobrecarregada e sem código todo-1; símbolos únicos por tabela,
   DC 0..11, AC tamanho 1..10 ou EOB 00/ZRL F0. Duplicatas de destino/classe são excluídas pelo
   perfil. Todas as tabelas referidas devem estar definidas antes de SOS; sem tabelas externas.
5. SOS único, Ns=N, length=6+2*Ns, componentes na mesma ordem do SOF, sem repetição, tabelas
   DC/AC existentes; Ss=0, Se=63, Ah=Al=0. Não basta procurar SOS ou EOI como substring.
6. Percorrer integralmente entropy até marcador: bytes ordinários e FF00 são dados; permitir
   fill FF limitado antes do EOI, sem confundir FF00 com marcador. Exigir pelo menos um byte
   de dados. RST/novo SOS/segmento após SOS são perfil não suportado. EOI FF D9 encerra exatamente
   no EOF, sem trailer/segunda imagem. EOF em segmento, escape ou sem EOI => truncated_jpeg.

Não contar MCUs nem validar que os bits codificam todos os blocos: corrupção de entropy ou remoção
de dados seguida de EOI pode passar este perfil. Portanto o resultado é elegibilidade estrutural
limitada, decoding=not_checked; não declarar todo JPEG falso detectável ou arquivo decodificável.

Motivos fixos: eligible_jpeg, unsupported_extension, not_regular_file, empty_file,
byte_limit_exceeded, invalid_jpeg_signature, truncated_jpeg, malformed_jpeg_segment,
unsupported_jpeg_frame, dimension_limit_exceeded, segment_limit_exceeded,
entry_changed_during_verification, read_failed, verification_timeout. Precedência: falha física
detectada prevalece sobre resultado do parse; depois limite/deadline, depois primeiro erro sintático.
Falhas físicas/read_failed/verification_timeout bloqueiam proposta, não são formatos excluídos.

Corpus sintético obrigatório: positivos grayscale e RGB baseline com DQT/DHT/SOS/dados/EOI,
APP/COM opacos e FF00; comparador decoder independente offline para os positivos (ferramenta de
teste, sem dependência runtime). Negativos: texto/PNG renomeados; SOI e SOI+EOI; length 0/1/além
do EOF; SOF repetido, ID repetido/tabela ausente, DQT zero/16 bits, DHT sobrecarregada/todo-1/
símbolos inválidos; SOS incompleto/tabela inexistente/parâmetros errados; EOI dentro de APP;
EOF após FF, FF00 ou payload; trailer/concatenado; SOF2 e CMYK; RST/DRI; 257 segmentos, 4 MiB+1,
fill de 65; dimensões 0, 20.000 e 7.000x7.000; arquivo 64 MiB+1; cancel/deadline e troca física.
Incluir caso de entropy semanticamente inválida com envelope aceito, para comprovar a limitação.
Fronteiras exatas (limite e limite+1), chunks partidos e determinismo também são obrigatórios.

## Seleção, IPC e encerramento v1 — MINOR-01

Preload expõe chooseMediaRoot(sessionId), prepareCataloging(sessionId, rootGrantId, recursive),
getPreparationStatus(sessionId, operationId), cancelPreparation(sessionId, operationId) e
listCatalogingCandidates(sessionId, proposalId, cursor, pageSize). Main deriva window_id da
janela confiável; nunca aceita window_id, path, MIME ou evidência do renderer. Campos exatos,
UUID canônico, extras rejeitados. Envelope autenticado da bridge permanece o de D04-01B.

| Rota Python | Params exatos | Result |
| --- | --- | --- |
| ingestion.select_root (só main após diálogo/confirm) | session_id, window_id, path, recursive=true, identity_reviewed=true | root_grant_id, root_id, expires_in_ms=300000 |
| ingestion.prepare | session_id, window_id, root_grant_id, recursive=true, client_request_id | JobStatus |
| ingestion.status | session_id, window_id, operation_id | JobStatus |
| ingestion.cancel | session_id, window_id, operation_id | job: JobStatus, cancel_effect |
| ingestion.page | session_id, window_id, proposal_id, cursor, page_size | proposal_id, items, next_cursor |

chooseMediaRoot retorna cancelled sem enviar select_root quando qualquer diálogo é cancelado.
prepareCataloging gera client_request_id UUID no main, reutiliza apenas para repetição técnica
idêntica; nenhum retry automático após timeout. Uma operação ativa; pedido distinto busy,
mesmo ID+conteúdo devolve a admissão anterior; ID com outro conteúdo invalid_request. Manter
até 32 admissões na sessão, depois resource_limit exigindo nova sessão. Grant monotônico de uso
único, nunca renovado implicitamente; expiração após admissão não cancela operação.

JobStatus: version=1, session_id, operation_id, revision crescente, state
(queued/running/cancelling/cancelled/completed/failed), phase
(snapshot/scanning/verifying/planning/cleanup/null), observed_count, verified_count,
excluded_count, total=null, terminal_reason (null/resource_limit/permission_denied/root_changed/
incomplete_coverage/worker_crash/protocol_failure/startup_timeout/execution_timeout/read_failed/
verification_timeout), proposal_id UUID ou null. Só completed tem proposal_id e phase=null;
completed não implica conjunto não vazio. Cancel_effect=accepted/already_cancelling/too_late.
Terminal é imutável; troca de sessão invalida IDs e revoga publicação. Polling 250 ms, sem push
de progresso ilimitado; revisão e contagens nunca regridem dentro da operação.

Página: até 50 itens, ordenados por relative_path preservando caixa/Unicode, cada um com
candidate_id, relative_path, state, reason, detected_format, profile, decoding. Nunca path
absoluto ou fingerprint físico. Cursor null inicia, depois token aleatório de 32 bytes opaco,
vinculado a sessão/janela/proposta/page_size/posição; token adulterado/cross-session é inválido,
repetição retorna mesma página. Até 2.000 itens e 2.000 posições de cursor por proposta, com
page_size fixo na primeira página (1..50); no tamanho 50 são até 40 páginas. Payload >256 KiB falha
resource_limit sem publicar proposta. Somente consulta após validação completa e reap.

Seleção de raiz abre todos os ancestrais por dirfd nofollow e mantém identidade observada até
admissão do worker, que revalida independentemente. Recusar raiz que contém catálogo/journals/
backups/cache; catálogo no diretório irmão continua permitido (não proibir todo path.parent).
Recusar raízes distintas aninhadas em ambos os sentidos e mesmo device/inode. Montagens internas
não autorizadas interrompem preparação, não são ignoradas como cobertura completa. Não resolver
symlink para ampliar grant. Aliases que não possam ser distinguidos com segurança são bloqueados.

LibraryRoot atual não persiste device/inode da raiz. Manter binding físico por root_id na sessão;
reutilizar só path/configuração exatos e identidade compatível, conferindo também localizações
conhecidas. Mudança de binding => root_changed, sem atualização silenciosa. Após relançamento,
identidade histórica indisponível exige nova revisão explícita no diálogo antes de reutilizar;
registrar ROOT_IDENTITY_UNAVAILABLE, sem alegar detecção histórica de troca. Não inferir igualdade
pela disponibilidade persistida, nem adicionar coluna/migração implícita neste contrato.

Multiplexação: leitor de stdin e leitor do worker só transportam frames em filas limitadas;
loop controlador, dono de SQLite, serializa comandos/transições/stdout. Worker via spawn sem
herdar conexão. Limites: fila de controle 16 frames <=64 KiB, resultado privado <=8 MiB,
progresso substituível em slot único, frames do worker <=64 KiB. Excesso protocol_failure.
RSS Linux /proc por PID observado a cada 50 ms, contabilizar filas/staging no controlador;
budget do controlador adicional de staging 8 MiB e no máximo duas cópias transitórias limitadas.
Medir overshoot, não prometer teto exato de RSS. Worker sem descendentes; falha do monitor
desabilita admissão ou encerra a operação, nunca continua sem supervisão.

Cancel/troca/close: 500 ms cooperativos, depois SIGTERM por 500 ms, SIGKILL e até 1.000 ms para
confirmar saída e reap. Slot continua ocupado se não houver reap: state=cancelling, phase=cleanup,
sem proposta e novas operações busy; não chamar failed terminal com processo ainda vivo.
Backend shutdown aguarda até 2.500 ms para cleanup e ACK; PythonBackend.shutdownTimeoutMs passa
explicitamente de 1.500 para 3.500 ms, com watchdog externo de 5.000 ms antes da escalada final
no grupo POSIX. Startup do worker 5 s dentro dos 30 s do job. Deadline externo não prova reap;
se syscall impedir saída, reportar unavailable/cleanup pendente, bloquear novo backend/trabalho
até confirmação de encerramento. Ensaiar crash do controlador, kill e ausência de órfãos no KDE.

## Evidência exigida e fora de escopo

Fixtures exclusivamente sintéticas: vazia, nested, links, raiz trocada, permission denied,
montagem fora de escopo, cancelamento, crash e worker resistente; 2.001 entradas, profundidade,
snapshot/proposta enormes, tempo/RSS e reap; JPEG truncado, assinatura enganosa, dimensões e
segmentos excessivos, leitura instável. Demonstrar zero INSERT Asset/FileLocation e ausência de
escrita em originais. Testar grants expirados/cruzados, respostas tardias e UI responsiva.
Medir custos e registrar limitações; sem monitor confiável, preparação indisponível nesse alvo.

Fora de escopo: apply, deduplicação, hash, merge de Assets, reconciliação completa, extração de
metadata, thumbnails, preview, migrações e suporte Windows não demonstrado. A observação de
reconexão de D04-01B permanece melhoria futura, sem refatoração oportunista neste incremento.

## Retorno Gemini e próxima revisão

Auditoria independente fornecida pelo solicitante sobre e5eccc4: PASS WITH CHANGES. MAJOR-01
tratado pelo tipo/validador de recorte separado e recomputação transacional futura; MAJOR-02
pelo perfil restrito e corpus explícitos; MAJOR-03 pela exceção de limite antes de sort;
MAJOR-04 pelo snapshot ro consistente e fechado antes de scan; MINOR-01 pelas rotas, grants,
paginação, sobreposição e timeouts acima. Encerramento dos achados depende de reauditoria.

Não se considera D04-02A implementado ou homologado por este contrato. Os gates existentes
não comprovam novos orçamentos, parser ou preparação de mídia. Esta revisão muda apenas este
documento; nenhum Asset, catálogo ou fotografia foi acessado. Build/smokes desktop não se aplicam.
Gates desta revisão: uv sync --locked PASS; uv run pytest PASS (359 testes, CPython 3.15.0);
uv run ruff check . PASS; uv run ruff format --check . PASS (105 arquivos); git diff --check
PASS; links locais sem destino ausente. Sem arquivos novos ou não rastreados. A referência T.81
foi obtida do W3C e consultada nos anexos B/C; não foi versionada. Gemini da revisão NOT RUN.
