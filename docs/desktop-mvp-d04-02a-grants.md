# D04-02A — Quarta entrega Python: seleção e grants de raiz

Data: 2026-11-04. Base: `1af6c8c2485f9bc69afc72f47f6c94e10ee4a33a`, worker/controlador
homologado pelo Gemini e integrado pela PR #15 com autorização explícita. Branch:
`feat/desktop-mvp-d04-02a-grants`. Referências: [contrato D04-02A](desktop-mvp-d04-02a.md)
e [worker/controlador](desktop-mvp-d04-02a-worker.md). ADRs e schema preservados.

## Entrega delimitada

`catalog_ingestion/root_grants.py` adiciona RootGrantService, um proprietário Python privado
por LibrarySession e janela confiável. Não é uma rota autenticada por si só: somente o futuro
main, após seleção nativa e confirmação explícita, poderá fornecer path e identity_reviewed.
Cancelar qualquer diálogo significa não chamar select. Nada é registrado nesse cancelamento.

- `select(params)` recebe exatamente session_id, window_id, path, recursive=true e
  identity_reviewed=true. Valida UUIDs canônicos, path absoluto canônico, escopo e proprietário.
  Abre cada ancestral por dirfd/O_NOFOLLOW, retém descritores até admissão/expiração e registra
  identidade física/mount. Não enumera árvores nem abre conteúdo de mídia.
- Recusa raiz contendo catálogo/journals ou destinos de backup/cache fornecidos pelo host;
  recusa também seleção dentro de um cache protegido. Catálogo e fotos como filhos irmãos do
  mesmo diretório continuam válidos. Comparações físicas complementam as lexicais para raízes
  distintas em ambas as direções. Mesmo device/inode ou mesmo device com mounts distintos e
  relação ambígua são recusados conservadoramente. Não há montagem privilegiada nos testes.
- Raízes já cadastradas são lidas em snapshot ro consistente e fechado antes da validação
  de filesystem. Uma raiz distinta ausente e lexicamente disjunta não tem alias físico atual;
  erros de permissão/symlink não são ignorados como ausência. Reuso exige path/configuração
  compatíveis e binding da sessão, quando disponível. Localizações conhecidas são conferidas
  por metadados O_PATH/nofollow, incluindo identidade scanner e tamanho/mtime disponíveis,
  sem ler conteúdo. Ausência/divergência recusa a operação, sem mudar disponibilidade persistida.
- Após relançamento não existe identidade histórica da raiz no schema. Exige revisão explícita
  e registra ROOT_IDENTITY_UNAVAILABLE no grant privado ao reutilizar raiz sem binding da sessão.
  O warning equivalente do planejador permanece nas evidências da proposta. Não promete detectar
  uma troca histórica quando não há evidência capaz de distingui-la.
- `Catalog.register_reviewed_root` executa comando curto BEGIN IMMEDIATE: compara o registro
  completo de raízes com o snapshot revisado e registra ou reutiliza o path exato. Divergência
  aborta/rollback. Nenhuma leitura de mídia ocorre nessa transação. Register_root legado mantém
  seu comportamento. Somente LibraryRoot pode ser inserida; nenhum Asset ou FileLocation.

Grant UUID opaco fica vinculado ao proprietário sessão/janela, raiz física, mount, path e
recursividade fixa. Resposta exata: root_grant_id, root_id, expires_in_ms=300000. Expiração usa
monotonic, é verificada na admissão e no tick ocioso e nunca renova grant implicitamente.
Limites conservadores: 32 grants vivos e 256 descritores retidos entre grants/candidato;
validações auxiliares usam uma cadeia temporária adicional de até 256 descritores. Registro
até 2.000 raízes/8 MiB, localizações até 2.000/8 MiB, caminhos conhecidos até 4.096 caracteres
com até 32 componentes. Excesso falha resource_limit sem proposta. Não são quotas de kernel.

`prepare(params)` recebe exatamente session_id, window_id, root_grant_id, recursive=true e
client_request_id. Revalida descritores, configuração, sobreposição e localizações antes de
admitir o worker já existente, que repete suas verificações independentemente. Consome e fecha
o grant na admissão; uma falha física ou tentativa recusada durante essa revalidação também
revoga o grant, exigindo nova seleção. Busy detectado antes da revalidação não o consome.
Mesmo client_request_id e conteúdo devolvem admissão anterior; outro conteúdo é invalid_request.
O histórico acompanha o teto de 32 admissões do controlador. Expiração após admissão não cancela
job. IDs cruzados/expirados/consumidos não autorizam nova operação. Sem retry automático.

## Fechamento e limites restantes

LibrarySession disponibiliza catalog_binding somente para Python privilegiado, fora do DTO.
Um close guard exclusivo revoga grants e propostas imediatamente e pede cancelamento. Close
retorna busy enquanto o worker ainda precisa de reap; a sessão/catálogo permanecem abertos.
O host deve continuar tick e repetir close após limpeza. Isso também protege LibraryLifecycle
na tentativa de troca; a sessão candidata é fechada se a anterior ainda estiver ocupada.

Seleção e conferência de metadados são síncronas e podem bloquear em syscalls de filesystem;
não há prazo/RSS externo para essa fase nesta entrega. O worker supervisiona a preparação após
admissão. A integração desktop precisa considerar essa fronteira antes de habilitar o fluxo,
sem anunciar que tick interrompe I/O bloqueado no host. Não há acesso a mídia pessoal aqui.

Filesystem e SQLite não participam da mesma transação: uma corrida detectada após commit da
configuração pode deixar uma LibraryRoot vazia, sem grant, Asset ou FileLocation. Não se tenta
apagar configuração automaticamente para desfazer um desfecho incerto. Revalidações não congelam
árvores; D04-02B continuará exigindo revalidação no commit de catalogação.

D04-02A permanece parcial. Diálogos nativos, bridge multiplexada, rotas IPC, preload/UI e os
prazos coordenados de shutdown Electron continuam pendentes. Nenhuma rota nova foi habilitada,
nenhuma migração/dependência/lockfile foi alterada e nenhum original foi modificado.

## Validação

Testes sintéticos exercitam registro/reuso, ausência de novos Assets/FileLocations, worker real,
expiração/consumo/deduplicação, IDs cruzados, paths/symlinks, ambas as sobreposições, mount
injetado, cache protegido, limites, thread proprietária, troca física de raiz/arquivo,
concorrência no registro, corrida pós-commit e cancel/reap no fechamento. Os testes não montam
filesystems nem simulam syscall permanentemente bloqueada. Gates finais: `uv sync --locked` PASS;
`uv run pytest` PASS (544 testes, 31 novos, sem skips; CPython 3.15.1; 49,19 s);
`uv run ruff check .` PASS; `uv run ruff format --check .` PASS (124 arquivos);
`git diff --check` PASS; no-index nos três arquivos novos sem whitespace (status 1 esperado).
Builds/smokes desktop não executados; homologação independente Gemini pendente.
