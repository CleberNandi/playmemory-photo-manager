# D04-02A — Quinta entrega: bridge multiplexada e IPC de preparação

Data: 2026-11-04. Base: `2dd26fe0aba82843631934a739db46e645d9bed6`, grants Python
homologados pelo Gemini e integrados pela PR #16 com autorização explícita. Branch:
`feat/desktop-mvp-d04-02a-bridge`. Referências: [contrato](desktop-mvp-d04-02a.md),
[worker](desktop-mvp-d04-02a-worker.md) e [grants](desktop-mvp-d04-02a-grants.md).
Sem mudança de ADR, dependência, schema ou lockfile.

## Entrega e fronteiras

- `desktop/transport.py`: pump Linux de pipes não bloqueantes, com selectors e espera ociosa
  de 10 ms. Um único proprietário lê/escreve os frames e executa transições/SQLite. Não foram
  adicionadas threads compartilhando conexões. Entrada parcial ou saída sem consumidor não
  bloqueiam o bombeamento. Controle limitado a 16 frames de 64 KiB, resposta individual até
  256 KiB, fila de saída até 16 respostas (4 MiB), leituras/escritas por passo até 64 KiB.
  Excesso de fila encerra o transporte e inicia limpeza; mensagens grandes são drenadas e
  rejeitadas, UTF-8 inválido não chega ao dispatcher. Buffers parciais são limitados.
- Bridge normal Linux passa a chamar LibraryDispatcher.tick inclusive sem requisições.
  Os leitores do stdin e do worker executam passos não bloqueantes na mesma thread proprietária;
  não há leitores auxiliares escrevendo stdout. Serve em memória e demo sem preparação conservam
  o contrato anterior. Rotas ingestion.* somente com token válido e laboratório habilitado.
- LibraryDispatcher compõe RootGrantService e suas cinco rotas exatas. Deriva o catálogo da
  sessão ativa; verifica janela e sessão, UUIDs e campos. O primeiro select vincula o serviço
  à janela, que deve ser derivada pelo main confiável. Não há rota de aplicação de catalogação.
- Durante worker ativo, consultas SQLite comuns devolvem busy antes de acessar filesystem/
  catálogo. Estado da biblioteca, status, cancel, replay idempotente e cleanup continuam sendo
  atendidos. Grants não são revalidados por I/O no replay de uma admissão já existente.
  Troca/close revogam a preparação e devolvem busy enquanto houver reap pendente; nenhum retry
  de mutação é automático. A sessão candidata não é aberta enquanto o worker ainda estiver vivo.
- Shutdown só responde accepted após cleanup confirmado e fechamento da biblioteca. EOF e
  falha de transporte também revogam/cancelam e continuam o bombeamento até reap. Uma tentativa
  de shutdown que exceder 2.500 ms devolve busy; o processo não abandona um filho pendente.

No Electron, `CatalogingController` recebe paths exclusivamente do diálogo de pasta seguido
por confirmação com Cancelar como padrão. A confirmação explicita recursividade, leitura,
registro de configuração, ausência de identidade histórica garantida e preservação de originais.
Cancelamento não envia select. Main gera window_id e client_request_id; só admite sessão atual,
valida IDs/cursores/tamanho/recursive e descarta respostas após mudança de sessão. Pedidos iguais
em voo são compartilhados; admissão bem-sucedida mantém seu ID para repetição idêntica. Falha de
transporte de desfecho desconhecido invalida o estado local, sem retry automático.

Os cinco handlers passam pelo mesmo trustedSender, URL exata, frame e aridade de D04-01B.
Preload expõe somente chooseMediaRoot, prepareCataloging, getPreparationStatus,
cancelPreparation e listCatalogingCandidates, sem invoke genérico, path, MIME, evidência ou
window_id vindos do renderer. Caminhos de userData/cache são fornecidos pelo main ao Python
como destinos protegidos. APIs retornam os DTOs públicos dos casos de uso; evidência privada e
paths absolutos não entram em páginas/status. Declarações renderer usam unknown até o consumidor
futuro validar os DTOs; nenhuma UI nova foi adicionada nesta fatia.

## Supervisor e limites de habilitação

PythonBackend admite até 16 requisições pendentes e 64 KiB por request. Grace de shutdown
passa a 3.500 ms, com watchdog de 5.000 ms para SIGKILL e até 2.000 ms adicionais de confirmação.
O prazo de startup também não impede a escalada de shutdown. Stop concorrente compartilha
promessa e start/restart ficam bloqueados até confirmação do encerramento do processo/grupo.
Falhas de protocolo ou timeout não limpam a referência de um processo ainda não encerrado.

O supervisor não envia sinais a um grupo numérico depois de recolher seu líder, pois esse ID
pode ser reutilizado. Grupo sobrevivente mantém estado indisponível/cleanup pendente; o worker
possui PDEATHSIG homologado na entrega anterior. Se o kernel impedir saída/reap, não há promessa
de término imediato nem liberação fictícia do slot. O aplicativo não apaga diretórios temporários
ou anuncia quit concluído quando stop rejeita por cleanup pendente.

APIs novas exigem `PLAYMEMORIES_DESKTOP_INGESTION_LAB=1` tanto no main quanto no Python e ficam
indisponíveis no demo. O laboratório usa userData/sessionData temporários. Sem essa variável,
seleção/preparação são recusadas. D04-02A continua parcial: faltam a UI de preparação/revisão,
a validação nativa KDE e a decisão de habilitação. Não há INSERT Asset/FileLocation ou alteração
de mídia. A seleção e conferência pré-admissão continuam síncronas e podem bloquear em syscalls;
a nova pump não torna essa fase cancelável nem interrompe I/O bloqueado no kernel. O monitor
somente é exigido enquanto há worker admitido, quando seleção e consultas SQLite são bloqueadas.

## Validação executada

- Python: uv sync --locked PASS; pytest PASS (554 testes, 10 novos, zero skips, CPython 3.15.1,
  53,09 s); Ruff check/format e whitespace PASS. Testes novos usam bridge real autenticada,
  worker e JPEGs sintéticos, incluindo ociosidade, linha parcial, EOF/shutdown, bytes inválidos,
  excesso de controle e backpressure sem parar tick.
- Desktop: pnpm install --frozen-lockfile, typecheck, test (13 arquivos / 84 testes, 9 novos),
  lint e build PASS. Runtime pnpm disponível nesta execução: 11.25.0, dentro do engines >=10;
  packageManager 12.15.0 e lockfile preservados. Testes cobrem cancelamento nativo simulado,
  escopo de sessão, IDs idempotentes, erro desconhecido sem retry e processo/grupo pendente.
- Electron headless: smoke D04-01B e novo smoke D04-02A IPC PASS; smoke demo/D03-01 PASS
  (73 Assets preservados, thumbnails, detalhes, paginação, resize, retry e missing preload).
  Flags de ambiente do ensaio: SMOKE=1, INGESTION_LAB=1 ou DEMO=1; execução Electron com
  --ozone-platform=headless --disable-gpu e --no-sandbox por executar como root neste runner.
  Sandbox/contextIsolation do produto não foram desabilitados no código. Isso não homologa
  sandbox do SO, GPU, Wayland ou diálogos nativos KDE. Esses últimos permanecem NOT TESTED.
- Medição sintética adicional: 128 JPEGs mínimos, sem entrada nova e saída deliberadamente
  backpressured; preparação completou em 640,6 ms, pico RSS observado do worker 36,8 MiB e maior
  intervalo observado de monitoramento 54,8 ms. O alvo é 50 ms, com atraso real medido; não é
  garantia de tempo real, quota de memória nem benchmark de fotografias de câmeras reais.

A primeira tentativa do smoke encontrou fixture dentro de userData e foi corretamente recusada
como unsafe_location. A fixture foi movida para um temporário irmão, mantendo a proteção;
smokes finais passaram. O smoke agora preserva exit code de falha após cleanup. Nenhuma mídia
pessoal, catálogo local, credencial ou artefato gerado é versionado. Gemini desta fatia pendente.
