# D04-01A — Lifecycle Python de bibliotecas persistentes

Data: 2026-10-29. Estado: implementação para auditoria independente Gemini; publicação em branch
autorizada pelo solicitante, sem homologação, PR ou merge. Base local e remota confirmada por
`git ls-remote`:
`main` em `52bc6c6f3073f444e8ed0e1f2b52443dd86a4dfb` (PR #9 integrada), árvore inicialmente limpa.
Branch de implementação: `feat/desktop-mvp-d04-01a`.

## Escopo e contratos

Implementa somente o primeiro incremento da seção 13 de [D04-00](desktop-mvp-d04-00.md).
Não altera schema/migrations, bridge, Electron, UI, scanner, ingestão ou galeria. Não acessa mídia,
não observa disponibilidade e não atualiza bancos antigos. ADRs 001–004 permanecem normativas.

- `catalog.validate_database(connection)`: conexão gerenciada, sem transação prévia. Valida runtime
  SQLite >= 3.37, histórico contíguo e checksums, user_version atual, DDL exato e estruturas
  interpretadas de tabelas/FKs/índices, integrity_check e foreign_key_check, numa transação de leitura.
  Constrói referência somente em memória pelas migrations existentes. Não executa DDL/DML no banco
  validado. Rejeita DDL editado mesmo quando semanticamente equivalente: política conservadora.
- `UpgradeRequiredError`: versão antiga reconhecida exige upgrade futuro explícito. Versão futura,
  schema divergente ou histórico falso são incompatíveis. Não chamar initialize_database para abrir.
- `connect(..., uri=False, timeout=5.0)`: parâmetros opcionais preservam os chamadores existentes;
  lifecycle usa URI escapada e timeout de 250 ms, UDFs e FKs da mesma fábrica.
- `LibrarySession.create(Path, known_media_roots=())`: destino absoluto novo, reserva 0600 por
  O_EXCL/O_NOFOLLOW; bootstrap somente nesse destino; valida antes de publicar sessão.
- `LibrarySession.open(Path, known_media_roots=())`: existente, probe ro/query_only, validação;
  conexão rw distinta testa BEGIN IMMEDIATE/rollback sem mutação persistente. Não existe fallback
  para rwc, upgrade ou recriação de banco ausente/corrompido.
- `query_connection`: ro/query_only gerenciada, pertencente à sessão. `command_connection()` é
  context manager com conexão rw separada, criada na thread proprietária, fechada ao sair; transação
  pertence aos casos de uso existentes de Catalog (BEGIN IMMEDIATE/commit/rollback). Trabalho não
  confirmado é revertido no fechamento. Comando aninhado ou close durante comando recebe busy.
- `LibraryLifecycle`: dono síncrono de uma sessão ativa. Candidato é validado antes de fechar a
  anterior; falha conserva a anterior. Troca fecha a antiga e avança geração monotônica; close
  invalida sessão e não apaga catálogo. SessionDescriptor contém UUID aleatório por ativação e
  nome do arquivo, sem path absoluto. Não é identidade durável do banco.
- `LibraryError.code`: códigos fixos not_found, permission_denied, corrupt, incompatible,
  upgrade_required, busy, unsafe_location, internal_error, invalid_request ou stale_session.
  Mensagem pública não contém path, SQL ou mensagem da exceção original; não há logs de payload.

Estas são APIs internas de Python confiável; conexão não pode ser exposta ao renderer. Não há novo
contrato IPC. Registro opaco de library_handle, preferência, diálogos, estados transitórios da UI,
grants e descarte de páginas/respostas são trabalho de D04-01B. Geração não é UUID persistido.

## Fronteira de filesystem e OBSERVATION-01

Suporte deste adapter: Linux com /proc/self/fd disponível. Outras plataformas falham fechado.
Ancestrais são percorridos por dirfd/O_DIRECTORY/O_NOFOLLOW, com descritores retidos. Arquivo
regular de link único fica aberto durante a sessão. Revalidação percorre novamente os ancestrais
e compara o diretório pai e st_dev/st_ino do catálogo. Symlinks, hardlinks e arquivos especiais são
rejeitados; URI é produzida por Path.as_uri, incluindo escaping de nomes Unicode, # e ?.

O handshake inspeciona descritores novos de /proc/self/fd após a fábrica SQLite retornar e exige
um descritor regular com st_dev/st_ino da seleção retida, além de revalidar o caminho. Isso acrescenta
evidência do arquivo efetivamente aberto; database_list/path sozinho não seria essa evidência.
Ausência de testemunho recusa a abertura, inclusive quando o VFS reutilizar descritor anterior.
Não é suporte a VFS alternativo, filesystem de rede, múltiplos escritores ou isolamento contra
processo hostil do mesmo usuário. Comparações antes/depois não detectam todo ABA; outro processo
do mesmo usuário pode interferir após o handshake, inclusive em journals. A auditoria deve avaliar
esta fronteira e seus testes adversariais; não se declara garantia absoluta de TOCTOU.

Não muda journal_mode. Por política conservadora inicial, qualquer -journal/-wal/-shm presente
recusa admissão com busy; auxiliar symlink/especial/múltiplos links recebe unsafe_location. Logo,
catálogo com recuperação pendente ou WAL presente exige tratamento próprio antes de ser admitido;
não há recuperação automática neste incremento. O probe ro antecede a conexão rw.

Falha de bootstrap conserva o arquivo novo com diagnóstico; nunca tenta unlink por pathname após
falha, pois a posse atual do nome pode não ser demonstrável. Nenhuma sessão é publicada em falha.
Registro/remoção assistida desse artefato será UX futura, não uma exclusão silenciosa.

Raízes conhecidas pelo chamador são checadas lexicalmente antes da reserva. Raízes registradas
no banco são consultadas após validação e comparadas sem acesso ao acervo. Não se descobre acervo
por varredura; raízes futuras/aliases físicos não podem ser inferidos. A seleção e checagem física
inversa de D04-02A continua obrigatória. Cache/backup/preferência não existem neste incremento.

## Validação e handoff

Fixtures exclusivamente sintéticas em diretórios temporários. Testes cobrem criação/reabertura,
bytes inalterados na abertura, exclusividade concorrente, query_only, escrita por conexão distinta,
rollback de comando incompleto, recursos fechados, sessões novas e troca/falha, versão antiga/futura,
checksums, índice/gatilho removidos, FK inválida, bytes inválidos, ausente, FIFO, hardlink, symlinks
de arquivo/ancestral/journal, substituição durante abertura SQLite, falta de testemunho do descritor,
lock exclusivo, thread incorreta, bootstrap falho e destino dentro de raiz conhecida/registrada.
O teste de permissão verifica negação real de os.open antes de testar o lifecycle, inclusive sob root.

Observações 02 e 03 do Gemini continuam em D04-02A e D04-04, respectivamente; nada neste diff altera
seu encaminhamento. Fluxo de entrega: Codex → auditoria Gemini da árvore exata → correções → PR
autorizada → merge somente mediante autorização específica. Não atribuir ao Gemini os gates locais.

Gates finais executados nesta árvore: `uv sync --locked` PASS; `uv run pytest` PASS
(346 testes, incluindo 29 novos); `uv run ruff check .` PASS; `uv run ruff format --check .`
PASS (101 arquivos); `git diff --check` PASS. Whitespace de cada arquivo novo verificado por
`git diff --no-index --check /dev/null -- <arquivo>`: PASS, saída vazia e status 1 esperado.
Runtime desta execução: CPython 3.15.0, Linux. Não houve alterações no lockfile/dependências.

Uma execução intermediária encontrou falha do harness de permissões: root sem capabilities não
podia fazer setgroups. O teste foi corrigido para comprovar negação efetiva de os.open também
nesse ambiente. Outra execução intermediária encontrou SIM117 no teste de thread, corrigido.
Todos os gates acima foram reexecutados depois dessas correções e da última mudança funcional.

Inspeção do escopo: seis arquivos de código/testes/documentação; nenhuma mídia, banco, cache,
credencial ou artefato gerado versionado. Build e smoke Electron/KDE NOT RUN: sem alteração
desktop neste incremento. Gemini NOT RUN: este documento é handoff, não parecer independente.
Pontos prioritários para auditoria: testemunho do fd SQLite e corridas, limites dos auxiliares,
validação sem upgrade/escrita, lifecycle e preservação da sessão anterior em falha.
