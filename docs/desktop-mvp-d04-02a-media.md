# D04-02A — Segunda entrega Python: JPEG, elegibilidade e recorte

Data: 2026-10-30. Base remota: `ec0c6cdb2450016c1609f600278a73b9da467861`,
primeira fatia homologada pelo Gemini com PASS e integrada pela PR #13 por autorização explícita.
Branch: `feat/desktop-mvp-d04-02a-media`. Referências:
[contrato homologado](desktop-mvp-d04-02a.md) e [primeira entrega](desktop-mvp-d04-02a-implementation.md).
AGENTS.md, implement-increment e quality-gates orientam implementação e validação; ADRs preservadas.

## Entrega

- `jpeg.py`: perfil jpeg_structural_v1 definido no contrato, sem dependência runtime nova.
  Leitura em chunks até 64 KiB, teto de 64 MiB por arquivo, 256 segmentos, 4 MiB de cabeçalhos,
  fill até 64 bytes FF, dimensões até 16.384 por eixo e 40 MP. Valida SOF0, DQT/DHT, referências
  de componentes/tabelas, SOS único, stuffing e EOI no EOF. Progressivo, restart, CMYK e outros
  perfis não são anunciados como suportados. APP/COM ficam opacos, sem extração EXIF.
- `media.py`: MediaEligibility privado, com UUID opaco, CandidateReference, observação exata,
  estado/motivo, formato, versão, decoding=not_checked e fingerprint físico quando houve leitura.
  Caminha da raiz por dirfd, O_NOFOLLOW, verifica identidade e cadeia de nomes, abre arquivo
  regular com O_NONBLOCK e compara device/inode/size/mtime/ctime antes/depois. Verifica mnt_id
  de /proc/self/fdinfo para não aceitar bind mount só porque st_dev coincide. Excluídos passam
  por metadados O_PATH sem seguir symlink nem ler conteúdo, incluindo diretórios vazios/FIFOs.
  Fds fechados em sucesso, erro e cancel. Linux somente, sem normalizar aliases silenciosamente.
- `scoping.py`: scope_catalogable_proposal puro e ScopedIngestionProposal separado, sem plano
  READY fabricado. Recalcula avaliação/plano e verifica cobertura, confinamento, impedimentos,
  diagnósticos e conjunto exato de elegibilidades. Aceita NON_FILE_OBSERVATION apenas nos casos
  previstos no contrato. Só novos JPEGs elegíveis entram nas referências; conhecidos permanecem
  conhecidos; falhas físicas/read_failed/timeout bloqueiam o conjunto. Fingerprint e orçamento
  canônico conservador de 8 MiB incluem original, elegibilidades, exclusões e referências.
- `_proposal_error` mantém a validação estrita legada; checagens de evidência extraídas em
  `_proposal_evidence_error`, reutilizadas pelo recorte. As APIs antigas não aceitam o novo tipo
  como autorização. Não há apply_scoped_ingestion, INSERT Asset ou FileLocation neste fluxo.

## Limites que permanecem

Aceite estrutural não verifica MCUs/coeficientes, pixels ou a semântica da entropy: o corpus
inclui corrupção aceita estruturalmente. Não apresentar elegibilidade como decodificabilidade.
Comparações de fstat não congelam arquivo, não detectam necessariamente mudança indetectável/
posterior e não atribuem identidade lógica, hash ou data de captura.

Os helpers são síncronos e destinados ao futuro worker descartável, não ao dispatcher da UI.
Checkpoints cooperativos usam 1 s por JPEG e 30 s por chamada de classificação, verificando cancel
antes de deadline. Não interrompem syscalls nem impõem RSS. Ainda falta o prazo global desde
snapshot/scan, monitor/reap externos e orçamento durante toda a construção da proposta no worker;
o recorte limita sua representação antes da publicação, não promete teto de memória do processo.
Identidade histórica da raiz e confirmação/grant são responsabilidade do controlador futuro;
o helper confere a raiz contra o ScanResult atual, não é autorização para leitura arbitrária.
Fingerprint canônico vincula evidências privadas; não autentica payload recebido de renderer.

Worker/controlador, grants/raízes/overlap, IPC e UI continuam pendentes. Nenhum fluxo real novo
foi habilitado no desktop, nenhuma migração/dependência/lockfile foi alterada e nenhuma fotografia
pessoal foi acessada. A recusa de mount é testada por injeção de identidade, não por montar
filesystems com privilégios. Não há homologação de outros sistemas operacionais nesta entrega.

## Validação

Corpus inteiro gerado em Python a partir de blocos 8x8 constantes; nenhum JPEG binário versionado.
Positivos grayscale e RGB são conferidos por FFmpeg offline quando disponível; ausência da
ferramenta é SKIP explícito, sem dependência runtime. Negativos e limites incluem tabelas,
marcadores, cabeçalhos, stuffing, truncamento, perfil, dimensões e tamanho. Testes físicos incluem
symlink, troca de raiz/inode/timestamps, mudança durante leitura, permissão, cancel, timeout,
mount de excluídos e ausência de vazamento de fd. Recorte testa preservação do plano, arquivos
aninhados/excluídos, conjuntos/IDs/observações adulterados e orçamento canônico.

Gates finais: uv sync --locked PASS; uv run pytest PASS (485 testes, 89 novos, sem skips nesta
execução; CPython 3.15.0); uv run ruff check . PASS; uv run ruff format --check . PASS
(116 arquivos); git diff --check PASS; no-index nos sete arquivos novos sem whitespace (status
1 esperado). Os dois positivos foram decodificados por FFmpeg offline. Verificação adicional:
5.000 envelopes sintéticos mutados/truncados deterministicamente, sem exceção não tratada do
parser, todos com códigos fixos. Não substitui corpus ou prova de correção de decoder.
Build/smokes desktop não reexecutados: nenhum arquivo desktop mudou. Gemini desta entrega NOT RUN.
Esta entrega não conclui D04-02A e não herda homologação apenas pela aprovação do contrato.
