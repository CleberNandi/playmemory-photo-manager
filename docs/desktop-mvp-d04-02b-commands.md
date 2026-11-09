# D04-02B — admissão, deduplicação e resultados por sessão

Base: PR #23 (`f2df725`). Controlador privado Python integrado ao serviço de
raízes/preparação. Ainda não implementa o processo de aplicação nem rotas IPC/UI.

## Contrato implementado

`RootGrantService.commands` pertence à mesma thread, sessão de biblioteca e
janela que a preparação. `admit` aceita exatamente session_id, window_id,
proposal_id, candidate_ids e client_request_id; IDs são UUIDs canônicos, a lista
contém até 100 únicos. Não recebe paths, MIME, kind, fingerprints nem objetos de
autorização enviados pela UI.

O controlador resolve a proposta privada somente se a preparação atual estiver
completa e sem worker ativo. Recupera o PreparationInput original e verifica
catálogo/identidade, vínculo da raiz, device/inode/montagem e sobreposição com
catálogo, auxiliares SQLite, cache e outras raízes. Esses checks são repetidos
em `claim`, antes de entregar o comando ao futuro executor.

Estados: queued, running, completed e outcome_unknown. Há um único slot de
admissão/execução. Uma chamada a claim consome o estado queued; não há segunda
execução pelo mesmo comando. Seleção e nova preparação ficam bloqueadas enquanto
há aplicação pendente. Pedidos antigos de preparação ainda podem recuperar sua
admissão histórica, sem iniciar outro worker.

`client_request_id` deduplica proposta e conjunto exatos de candidatos, sem
depender da ordem recebida. Mesmo ID com conteúdo diferente é rejeitado; mesmo
conteúdo retorna o estado/resultado existente antes de reconsiderar admissão.
São mantidos no máximo 32 pedidos admitidos, até encerrar a sessão; no limite,
é necessário abrir nova sessão explícita. Rejeições antes da admissão não
consomem esse histórico.

## Resultado e incerteza

`finish` exige que o executor confirme o reap do worker. Confere run/raiz/recorte,
conjunto integral de candidatos, disposições, UUIDs e independência de Assets e
localizações criados. Resultado incompleto, adulterado ou incompatível vira
outcome_unknown, nunca sucesso presumido ou prova de ausência de escritas.

O DTO público inclui apenas command_id, estado e resultado com candidate_id,
disposição, asset_id/location_id e diagnóstico fixo. Não expõe paths físicos,
fingerprint, mensagens internas ou a proposta. Devolve cópias para não permitir
alteração do resultado armazenado.

Depois de concluído, o comando libera referências à proposta/seleção privada e
retém somente assinatura e DTO limitado. Assim, o histórico não mantém 32
propostas de até 8 MiB em memória. No máximo um comando conserva payload privado.

`worker_failed` também exige reap confirmado. Após falha de worker ou resultado
incerto, novos comandos e novas preparações ficam suspensos. A repetição exata
do pedido continua retornando o resultado incerto armazenado; não executa retry.
Não há journal durável: após crash é necessária recuperação explícita da
biblioteca e nova preparação para observar os caminhos persistidos.

Fechar a sessão revoga comandos queued sem executá-los. Running impede o
fechamento até reap e resultado/falha: não confundir timeout com encerramento.
A solicitação já revoga grants e bloqueia novas admissões/preparações, mesmo
se o chamador precisar tentar o fechamento novamente depois de receber busy.
Finalizada a sessão, IDs antigos não podem ser consultados ou reutilizados.
A admissão usa o vínculo da preparação já autorizada; não ressuscita grants
consumidos nem aceita root_grant_id como autorização de escrita.

## Limites desta entrega

Não há chamada síncrona de aplicação no loop do bridge, novo botão ou canal IPC.
Os testes executam o núcleo diretamente apenas no harness sintético. O próximo
incremento deve supervisionar um processo próprio (entrada/saída limitadas,
monitor de RSS/tempo, confirmação de exit/reap e validação da identidade do
catálogo no executor), depois habilitar confirmação explícita no main e os
contratos estreitos de IPC/UI. Sem isso, não anunciar catalogação utilizável.

Revisão humana e confirmação de escrita ainda não são fornecidas por este
controlador: o digest e a admissão não demonstram consentimento humano por si só.

## Testes

17 testes novos usam sessões reais de bibliotecas e preparação em workers com
JPEGs sintéticos. Cobrem execução do núcleo + repetição sem duplicação, payload
alterado com mesmo ID, ordem da seleção, cópia defensiva de resultados, consumo
único, limite de 32, fechamento queued/running, reap obrigatório, sessão/janela
ou thread alheias, raiz/proposta invalidadas, suspensão, resultado parcial ou
adulterado e retenção apenas do DTO após conclusão. Nenhuma mídia pessoal.

Gates: `uv sync --locked`, 632 testes Python (17 novos), Ruff, formatação e
whitespace incluindo arquivos novos; typecheck desktop, 104 testes, ESLint e
build aprovados. Teste gráfico do novo comando não aplicável: não há rota de
aplicação habilitada nem novo controle visual nesta revisão.
