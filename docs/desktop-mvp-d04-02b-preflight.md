# D04-02B — preflight físico do lote selecionado

Base: PR #21 (`49d4ea0`). Incremento dependente da autorização do recorte;
não implementa aplicação nem confirmações de UI/IPC.

## Contrato

`preflight_scoped_ingestion` é um context manager privado do backend. Primeiro
revalida a autorização, depois abre raiz/ancestrais por descritores sem seguir
links e exige device/inode e mount ID esperados. O mount ID deve vir do vínculo
privado da preparação, nunca do renderer nem de uma observação nova escolhida
para substituir a identidade anteriormente autorizada.

Somente os JPEGs selecionados são reabertos pelo verificador estrutural já
existente. Exige resultado elegível, formato JPEG e fingerprint idêntico ao da
preparação (raiz/device/inode/tamanho/mtime/ctime, antes e depois). Alterações
físicas detectáveis bloqueiam o lote inteiro, não viram exclusões silenciosas.
Nenhum arquivo não selecionado é reclassificado como novo candidato.

A raiz permanece retida durante o contexto. `check_root()` verifica os
ancestrais, a identidade do descritor e reabre o caminho para conferir a montagem
atual; um descritor antigo não basta para detectar uma montagem nova no mesmo
caminho. A aplicação futura deve executar essa checagem novamente no limite da
transação. Após a saída do contexto a prova expira e os descritores são fechados,
inclusive em falha, cancelamento ou exceção do chamador.

## Limites

- Linux, mesmos confinamento e perfil JPEG do preparador; até 100 selecionados
  pela autorização. Cada cadeia absoluta mantém no máximo 128 diretórios.
- Deadlines cooperativos de 1 segundo por arquivo e 30 segundos por lote.
  Não interrompem I/O bloqueado no kernel nem limitam RSS ou vida do processo;
  a integração deverá usar processo supervisionado, não a thread da UI.
- Preflight fora de transação SQLite. Não abre banco, não grava Assets ou
  FileLocations, não altera originais e não calcula/promove SHA-256.
- Descritores e fingerprints não congelam o conteúdo contra escritores externos.
  Mudanças após a checagem continuam possíveis; esta entrega não promete snapshot
  físico nem bytes atuais garantidos no instante de commit.
- Não substitui grant/sessão válidos, política de sobreposição catálogo/cache,
  recomposição lógica sob BEGIN IMMEDIATE ou deduplicação de comandos.
- A prova é objeto privado efêmero; não é credencial assinada, não é persistida
  e não pode ser recebida pronta do renderer.

## Testes

19 cenários sintéticos cobrem preservação de bytes/mtime/banco, alteração com
mtime restaurado, desaparecimento/substituição, symlink/FIFO/ancestral symlink,
troca de raiz antes/depois do preflight, mount ID divergente, simulação de
remontagem com descritor retido, seleção vazia, cancelamento/timeout, decisão
adulterada e fechamento de descritores em sucesso/falha/exceção do chamador.
Permissão negada é simulada por falha de I/O; não é prova de chmod efetivo sob
usuário privilegiado. Nenhum teste usa mídia pessoal ou montagem real privilegiada.

Gates executados: `uv sync --locked`, 595 testes Python (19 novos), Ruff,
formatação e whitespace incluindo novos arquivos; typecheck desktop, 104 testes,
ESLint e build aprovados. Nenhuma nova interface gráfica foi implementada;
smokes nativos de aplicação permanecerão para a integração transacional/IPC.
