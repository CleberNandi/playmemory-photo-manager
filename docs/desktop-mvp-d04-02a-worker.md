# D04-02A — Terceira entrega Python: worker e controlador

Data: 2026-11-04. Base: `cf1bc0b251838d62e989549e6e95e247590ed2f8`, segunda
fatia homologada pelo Gemini e integrada pela PR #14 por autorização explícita.
Branch: `feat/desktop-mvp-d04-02a-worker`. Referências: [contrato](desktop-mvp-d04-02a.md),
[fundação](desktop-mvp-d04-02a-implementation.md) e [mídia](desktop-mvp-d04-02a-media.md).

## Entrega delimitada

- `preparation.py`: controlador privado Linux, serializado na thread proprietária, com um slot
  de processo, até 32 admissões idempotentes, status versionado, vínculo sessão/janela, cancelamento
  irrevogável e paginação de resultados voláteis. Não é uma API autorizada para o renderer.
  `PreparationInput` deve vir de um futuro grant validado; suas validações de forma e identidade
  não substituem seleção nativa, consentimento ou checagem de sobreposição de raízes cadastradas.
- `preparation_worker.py`: executável fixo via `sys.executable -m`, sem shell, sem pool, sem
  credenciais herdadas e com `close_fds=True`. Instala `PR_SET_PDEATHSIG=SIGKILL` e verifica a corrida
  de morte do pai. Recebe uma única seleção privada, captura snapshot somente-leitura, fecha SQLite,
  abre raiz por descritores, escaneia com limites e identidade de mount, verifica JPEG e produz o
  recorte existente. Não cria Asset/FileLocation, cache, sidecar ou alteração de original.
- `worker_wire.py`: transporte JSON privado com tipos locais permitidos, sem pickle/import dinâmico,
  rejeição de chaves duplicadas e recomputação da proposta recebida. Resultado de até 8 MiB,
  dividido em frames de até 64 KiB; sequência, tamanho e SHA-256 são conferidos. O digest detecta
  inconsistência do transporte, não autentica conteúdo oriundo do renderer.
- Scanner aceita opcionalmente um descritor emprestado da raiz e `mount_id`; duplica o descritor
  e preserva o original, recusando mudança de mount antes de enumerar cada diretório. Chamadores
  existentes conservam o comportamento anterior. Snapshot pode exigir a identidade física do
  catálogo previamente selecionado, antes de conectar SQLite.

## Supervisão e publicação

O host deve chamar `tick()` em seu loop multiplexado, inclusive ocioso, a cada no máximo 50 ms.
Não há thread monitora autônoma. Startup de 5 s e prazo global de 30 s incluem snapshot/scan e
classificação; RSS acima de 256 MiB inicia falha/limpeza. O monitor vincula o PID do subprocesso
à identidade exposta por procfs usando PPid e NSpid, inclusive com namespaces diferentes; recusa
admissão/continuidade quando a observação necessária não pode ser demonstrada. Inventário limitado
a 4.096 processos. `peak_worker_rss` e `max_monitor_gap` são diagnósticos privados para medição.

RSS é amostrado, não uma quota imposta pelo kernel: há overshoot entre amostras e durante a
limpeza, e alocações breves podem escapar da amostragem. Orçamento canônico do recorte e orçamento
do transporte são rechecados antes da publicação, não constituem teto da memória transitória
na construção. O transporte tipado pode ser mais restritivo que o JSON canônico de domínio.

Cancelamento usa SIGUSR1 cooperativo após ready; decorridos 500 ms, SIGTERM; após 1.000 ms no total,
SIGKILL. `shutdown()` tenta drenar por até 2.500 ms. Se o kernel não permitir recolher o filho,
retorna False e mantém o slot em limpeza: o host deve continuar bombeando `tick()` e não anunciar
fechamento concluído. SIGKILL não promete interromper imediatamente I/O ininterruptível do kernel.

Somente depois de saída, EOF e reap confirmados são reconstruídas e revalidadas as evidências,
identidades, contadores e páginas públicas. Cancel/erro descartam resultados parciais e tardios.
Páginas contêm nomes relativos, estados e motivos, sem paths absolutos/fingerprints; tamanho
fixado na primeira página, até 50 itens e 256 KiB. Cursores aleatórios de 32 bytes ficam vinculados
à proposta/sessão/janela do controlador e não sobrevivem à substituição ou ao encerramento.

## Limites desta entrega

D04-02A continua parcial. Não foram adicionados grants/seleção de raiz, multiplexação da bridge,
rotas IPC, preload ou UI. O loop síncrono atual não chama este controlador e o fluxo real permanece
inativo. Na próxima fatia será necessário integrar o bombeamento ocioso e a coordenação de troca/
fechamento de sessões antes de habilitar leitura de mídia, além de ajustar o timeout Electron de
1.500 para 3.500 ms e demonstrar seu watchdog de 5.000 ms. Esse ajuste não foi antecipado aqui.

Identidade física e mount são evidências atuais, não identidade lógica ou congelamento do acervo.
O worker não é sandbox de segurança contra execução de código arbitrário. A morte do pai mata o
worker; o recolhimento de órfãos depende do init/subreaper do sistema. O teste de morte do pai usa
um subreaper isolado e confirma também o reap, sem alterar o processo pytest.

## Validação

Testes sintéticos cobrem processo real, publicação após reap, páginas/cancel/deduplicação, escopo
sessão/janela, entrada de 2.001 nomes, troca física, descritor emprestado/mount, falha de spawn e
configuração de pipes, crash, protocolo malformado, payload adulterado e ausência de token/fd
herdados. Limites temporais são exercitados por relógio controlado; RSS tem teste injetado e teste
com alocação real mantida acima de 256 MiB. Não simulam syscall permanentemente bloqueada no kernel.

Gates finais: `uv sync --locked` PASS; `uv run pytest` PASS (513 testes, 28 novos,
sem skips, CPython 3.15.1; execução completa em 42,07 s); `uv run ruff check .` PASS;
`uv run ruff format --check .` PASS (121 arquivos); `git diff --check` PASS; no-index
nos cinco arquivos novos sem erros de whitespace (status 1 esperado). Builds/smokes desktop
não executados nesta fatia Python. Nenhuma fotografia pessoal ou catálogo pessoal foi acessado;
sem dependência, migração ou lockfile novo. Homologação independente Gemini pendente.
