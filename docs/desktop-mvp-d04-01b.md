# D04-01B — Jornada desktop de bibliotecas

Data: 2026-10-30. Base: main em `94ed73621daee4d72d28fc54c3a74fa04a1f747c`, PR #10 integrada.
Branch: `feat/desktop-mvp-d04-01b`. Implementação para auditoria; sem parecer Gemini, PR ou merge.

## Plano, autoridade e escopo

Instruções carregadas: AGENTS.md, implement-increment e quality-gates locais; ADR-004;
D04-00 §§4–5, 12–14 e handoff D04-01A. Fluxo: Codex → smoke KDE/auditoria Gemini → PR →
merge expressamente autorizado. Os achados corrigidos/retirados de D04-01A permanecem preservados.

Plano executado: adaptar o lifecycle Python à bridge; introduzir seleção/preferência privadas
no main; vincular consultas à sessão; oferecer controles React; testar falhas e isolamento.
Não há migration, dependência, scanner, decoder, ingestão, worker ou funcionalidade de duplicatas
nova. A galeria existente apenas recebe conexão/sessão ativa: D04-03 ainda exige seu aceite próprio.

## Contratos e responsabilidades

- O processo Python normal inicia sem conexão SQLite, no estado no_library; não cria mais catálogo
  em memória implicitamente. Demo permanece explícito e usa somente fixtures sintéticas.
- LibraryDispatcher possui LibraryLifecycle na mesma thread do transporte. Métodos privilegiados
  library.create/open recebem somente path da seleção nativa e library_handle UUID do registro
  privado do shell; library.close exige session_id; library.state não recebe parâmetros.
- Bootstrap, validação e vínculo de inode são os de D04-01A. O antigo helper que aceitava
  user_version isoladamente foi removido; inclusive --catalog usa LibrarySession. CLI --catalog
  permanece um modo explícito de compatibilidade, não a entrada do supervisor normal.
- Consultas gallery.list, asset.details, thumbnail.get e duplicates.* exigem session_id no modo
  normal. Python compara com a sessão corrente antes de resolver a conexão. Falha de abertura
  preserva a sessão anterior; close e saída fecham recursos. Exceções públicas usam códigos fixos.
- Parser rejeita chaves duplicadas/extras, profundidade >12, IDs de correlação >128 caracteres e
  mensagens >64 KiB. A leitura de linha é limitada e drena uma mensagem excedente antes da próxima.
  Saída permanece limitada a 256 KiB. Nenhum SQL, URI, segredo ou diagnóstico privado é devolvido.
- Electron main valida a janela, mainFrame e URL esperada em todas as rotas IPC. Canais têm
  aridade/objetos restritos; preload não expõe invoke genérico, SQL ou método com path da UI.
- showSaveDialog seguido de confirmação cria; showOpenDialog de arquivo único abre. Cancelamento
  não ativa nem grava seleção; criação exclusiva Python nunca substitui um arquivo existente.
  Seleção de pasta de mídia ainda não existe. O diálogo explica separar catálogo e acervo.
- LibraryController mantém estado/registro privado, bloqueia ações concorrentes e vincula queries
  à sessão/epoch. Resposta tardia da sessão substituída é rejeitada; selecionar/cancelar um diálogo
  ainda não invalida uma leitura já admitida da biblioteca anterior. Timeout/erro de transporte em mutação
  invalida a sessão visível: não presume que a ação falhou nem repete comandos automaticamente.
- Preload captura a sessão para cada consulta. React remonta o conteúdo inteiro quando muda o
  session_id, descartando páginas, detalhes, seleção e fila de thumbnails da montagem anterior,
  mesmo com UUID de Asset igual nos dois catálogos. Demo conserva o contrato de navegação anterior.

## Preferência e recuperação

LibraryPreferences guarda selection.json versionado na pasta privada library-state do userData.
Contém somente version=1, reopen boolean e última seleção {path, handle} ou null. Não guarda token,
grant, plano, job ou identidade global do catálogo. Não expõe esse registro ao renderer.

Leitura ausente não cria diretórios. Validação rejeita symlinks, proprietário/permissões inseguros,
arquivos não regulares/hardlinks, registros >16 KiB e schema desconhecido. Escrita usa temporário
exclusivo 0600 em pasta 0700, sync do arquivo e rename atômico; limpeza só do temporário gerado.
As verificações de ancestrais não prometem isolamento contra processo hostil do mesmo usuário.
Atomicidade da troca não é garantia de durabilidade contra perda de energia (sem fsync do diretório).

Reabrir ao iniciar é opt-in, inicialmente falso. Se habilitado, o shell envia somente open da
seleção anterior ao novo backend: nunca cria, procura substituto ou migra. Erro mostra unavailable
com diagnóstico e opções de escolher/reconectar. Preferência inválida leva a no_library com aviso.
Falha ao salvar preferência mantém biblioteca ativa e aviso visível. Close conserva a preferência;
Esquecer última biblioteca salva registro vazio sem fechar/apagar o catálogo ativo.

Estados transitórios de abertura/fechamento são apresentados pelo React durante a Promise; o
estado autoritativo do controlador é active/no_library/unavailable. Session UUID é novo em cada
ativação; geração Python é monotônica dentro daquele processo, não uma identidade durável.
Não há monitoramento físico contínuo do catálogo ou do acervo, nem retry automático de mutação.
Retry de galeria tenta primeiro a consulta na sessão ativa; só reconecta o backend diante de
falha de transporte/estado indisponível. Não abandona uma sessão válida só para repetir uma leitura.

## Testes e validação

Python: sessão vinculada, create/open/close/troca, falha conserva anterior, sessão antiga recusada,
parâmetros extras/inválidos, parser duplicado/profundo/excedente e erro sem path privado.
Desktop: cancelar sem efeito, preferência/reabertura, falha de gravação, resultado desconhecido,
queries tardias, ações simultâneas, sender/frame/origem, permissões e symlink de preferência,
remontagem React e teste com supervisor Python real offline, incluindo restart e sessão antiga.

Gates automatizados executados nesta árvore: uv sync --locked PASS; uv run pytest PASS
(359 testes); uv run ruff check . PASS; uv run ruff format --check . PASS; git diff --check PASS;
whitespace individual dos 11 arquivos novos PASS. Desktop: pnpm install --frozen-lockfile,
typecheck, test (75 testes em 12 arquivos), lint e build PASS. Runtime desta execução: Python
3.15.0, Node 24.22.1, pnpm 11.25.0; lockfiles e dependências inalterados (packageManager declarado
continua pnpm 12.15.0). Usar essa versão declarada no KDE quando disponível.

Falhas intermediárias tratadas: restauração inicial de uv-build por timeout de rede; teste de
galeria comparava tuple interno com list JSON; teste demo interceptava helper removido; lint de
erro capturado e efeito React. A árvore final passou nos gates após correções, incluindo o
teste com supervisor real e exceção correta quando executado por python -m. Nenhum resultado
intermediário falho foi contado como PASS. Os gates de D04-01A não substituíram esta execução.

## Smoke Electron e homologação KDE pendentes

`pnpm --dir desktop smoke` exercita preload/IPC/supervisor/Python reais com seleções exclusivamente
sintéticas do harness (cancelar, criar A, criar B/trocar, fechar, abrir A, preferir reabertura,
restart do backend, rejeitar ausente e esquecer). Ele simula a origem da seleção nativa; portanto
não comprova showOpenDialog/showSaveDialog. Usa userData temporário próprio, removido ao sair.
`pnpm --dir desktop smoke:demo` conserva o smoke do demo com a allowlist de preload atualizada.

Neste ambiente, smoke normal foi tentado e bloqueado pelo Electron: execução como root não é
suportada com sandbox. Não se alterou sandbox para obter PASS. Demo e diálogos nativos NOT RUN
pela mesma limitação. Não há evidência de execução Electron/KDE desta revisão.

No KDE, usuário normal, raiz do repositório:

```bash
uv sync --locked
pnpm --dir desktop install --frozen-lockfile
pnpm --dir desktop smoke
pnpm --dir desktop smoke:demo
PLAYMEMORIES_DESKTOP_LIBRARY_LAB=1 pnpm --dir desktop start
```

O último comando usa diálogos nativos e userData temporário separado, sem carregar preferência
pessoal nem aceitar path de fixture por argumento/env. O destino inicial do diálogo fica nessa
área temporária: crie A.sqlite3 e B.sqlite3 ali. Não escolha fotos, acervos ou catálogos pessoais.
Essa área é removida ao encerrar; o laboratório não testa persistência entre relançamentos do app.
Persistência entre processos ainda precisa de homologação própria; restart do backend e leitura
de preferência persistida estão cobertos separadamente pelos testes/smoke descritos acima.

Roteiro nativo: cancelar Criar (nenhum catálogo); criar A e conferir nome/sessão; cancelar Abrir
(preserva A); tentar criar sobre A (recusa sem overwrite); criar B (sessão nova); fechar; abrir A
(UUID de sessão novo); marcar Reabrir ao iniciar; esquecer seleção (catálogo continua ativo);
fechar e conferir no_library. Conferir foco, mensagens, ausência de overflow em 760×520 e ausência
de processos órfãos após encerrar. Registrar resultado real, inclusive NOT RUN/inconclusivo.

Gate de publicação de PR permanece pendente de auditoria e evidências desktop aplicáveis.
