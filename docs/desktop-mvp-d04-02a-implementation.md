# D04-02A — Primeira entrega de implementação: coleta e snapshot limitados

Data: 2026-10-30. Base: `f3d6a7c85b91a33b7900ba94debe57eddf94f4ad`, contrato
homologado e integrado pela PR #12 por fast-forward autorizado. Branch:
`feat/desktop-mvp-d04-02a`. Contrato: [D04-02A](desktop-mvp-d04-02a.md).

## Escopo implementado

- Scanner: ScanLimits opcional em ScanOptions (defaults 2.000 entradas e profundidade 32).
  Sem limites, comportamento legado preservado. No modo limitado, o contador pertence à
  chamada, inclui nomes antes de stat e não reinicia por diretório. A sentinela de excesso
  interrompe antes de sort/stat/leitura; ScanResourceLimitError expõe reason/count/depth,
  sem paths ou ScanResult falsamente completo. Limites valem também no fallback, que não
  ganha homologação de confinamento por isso. Cancel pode interromper a própria enumeração.
- Leitura de catálogo para o futuro worker: read_library_connection usa a mesma seleção
  retida por descritores e testemunho SQLite de D04-01A, somente mode=ro/query_only, sem
  probe rw ou ativação de sessão. Recusa WAL antes de connect, valida schema/integridade,
  aplica SQLITE_LIMIT_LENGTH e revalida o destino no retorno; fecha conexão e descritores.
- capture_catalog_snapshot: BEGIN explícito, páginas até 100 localizações, máximo 2.001
  linhas carregadas para detectar excesso, orçamento canônico incremental conservador de
  8 MiB e limite de célula/linha SQLite. Assets únicos são carregados em lotes até 100 por
  cursor iterado do repositório, com orçamento verificado a cada registro antes do acúmulo.
  IDs ausentes são recusados. Snapshot inclui
  todos os registros da raiz no escopo recursivo `.`. Rollback e close antes de devolver.
- prepare_from_snapshot: composição pura de evaluate/plan_changes sem capacidade SQLite.
  O fluxo legado prepare_ingestion e os campos/digest lógico de read_version são preservados.
  Planner, autorização e aplicação permanecem estritos, inclusive para diretórios.

O orçamento de bytes usa uma reserva fixa de 512 bytes para envelope/scope/digest mais JSON
ASCII canônico de cada registro (todos os campos, não só os do digest). É conservador: pode
recusar um snapshot ligeiramente menor que 8 MiB, nunca anuncia um teto exato de RSS. SQLite
limita células antes da materialização Python; orçamento agregado limita acúmulo. Validação de
integridade/schema pode custar tempo e memória: estes helpers síncronos não são seguros para
despacho direto da bridge. O futuro controlador/worker ainda deve impor deadline/RSS externo.

## Limite desta entrega e próximos passos

Esta é a primeira base Python de D04-02A, não a conclusão do incremento funcional. Nenhuma
rota, seletor ou preparação real foi habilitada no desktop. Permanecem por implementar:
perfil JPEG/corpus, MediaEligibility/ScopedIngestionProposal, controlador/worker/reap e
monitoramento, grants/raízes/sobreposição, IPC e UI/paginação. Limite da proposta final só pode
ser validado com essas estruturas. Aplicação transacional de candidatos é D04-02B.

Nenhuma migração, dependência ou lockfile mudou. Testes não usam fotografias pessoais nem
modificam originais; bancos e árvores são sintéticos temporários. A API de snapshot é Python
privilegiada, não aceita autorização do renderer e não substitui grants ou identidade da raiz.
O scanner legado ainda não valida toda a cadeia de ancestrais nem limites de mount; não se
atribui a esta entrega o futuro confinamento da seleção desktop.

## Validação e auditoria

Testes novos cobrem contagem global, fronteiras 2.000/2.001 e 32/33, interrupção de iterador
antes de ordenação ilimitada, links/FIFO/falhas, cancelamento e fechamento de fd; snapshot
consistente, bloqueio de commit externo, lotes de Assets, teto de registros/bytes/células,
SQLITE_TOOBIG, pureza/comparação com legado, close após erro e recusa de WAL/symlink/troca de inode.
Gates finais: uv sync --locked PASS; uv run pytest PASS (396 testes, 37 novos, CPython 3.15.0);
uv run ruff check . PASS; uv run ruff format --check . PASS (109 arquivos); git diff --check
PASS; no-index nos quatro arquivos novos sem mensagens, status 1 esperado. Build/smokes desktop
não reexecutados: nenhum arquivo desktop mudou. Auditoria Gemini desta implementação NOT RUN.

Durante o desenvolvimento, um argumento do contador foi inserido em chamada incorreta, corrigido
antes de reexecutar os testes legados. Um teste agregado inicialmente não atingia o orçamento e
foi ampliado; também foram corrigidos imports/formatação e consumo de páginas antes da contagem
de bytes. Nenhuma execução intermediária falha foi contada como PASS.
