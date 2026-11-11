# Duplicatas exatas, revisão persistida e plano dry-run — Duplicate Integration 01A/01B

## Escopo e API

`playmemories_photo_manager.duplicates.find_exact_duplicates(connection)` consulta Assets,
FileLocations e LibraryRoots existentes, faz pré-agrupamento pelo tamanho observado no filesystem
e calcula SHA-256 integral somente para tamanhos repetidos. O retorno imutável contém grupos,
membros ligados aos IDs do catálogo, identidade física POSIX, contagem de links e diagnósticos de
cobertura. A operação não persiste hashes, não funde Assets e não altera arquivos.

Cada localização permanece um membro independente, inclusive quando várias pertencem ao mesmo
Asset. `physical_copy_count` conta pares distintos `(device, file_id)`; assim, duas localizações
hardlinkadas continuam visíveis, mas não são apresentadas como duas cópias físicas independentes.
Grupos e membros têm ordenação determinística.

## Revisão humana e plano 01B

`save_exact_duplicate_decision(connection, *, sha256, keep_location_id, reason)` executa uma nova
detecção, exige que a ocorrência preservada pertença ao grupo exato verificado e persiste, em uma
transação, a escolha explícita, o motivo não vazio, todos os membros e um fingerprint SHA-256
canônico das evidências. O fingerprint inclui IDs de Asset, FileLocation e raiz, path relativo,
tamanho, hash e identidade física observada. Salvar uma nova escolha para o mesmo grupo marca a
anterior como `stale`, sem apagá-la.

`generate_exact_duplicate_plan(connection)` executa novamente `find_exact_duplicates()`, compara
as evidências físicas e SHA-256 com a decisão persistida e retorna grupos determinísticos nos
estados `pending`, `ready`, `blocked` ou `stale`. Divergência marca a decisão como `stale`, mantém
seus membros históricos e nunca atualiza silenciosamente o snapshot salvo. Decisões stale
continuam consultáveis no plano até uma nova revisão explícita.

Cada membro indica separadamente `keep`, candidato teórico, proteção e hardlink. Neste incremento,
um Asset é protegido quando possui álbum, tag, anotação, metadata ou thumbnail catalogada. O grupo
é bloqueado por cobertura incompleta, hardlink, mesma identidade física atribuída a Assets
distintos, candidato protegido ou ausência de uma ocorrência preservada revalidada. Uma decisão
humana não remove bloqueios.

O plano é somente consultivo: `action_authorized` e `operations_performed` são sempre `False`.
Não existe executor, autorização física, movimentação, exclusão, restauração ou consolidação.

## Cobertura e confinamento

Somente localizações `present`, de tipo `file`, em raízes `available` são elegíveis. Localizações
offline, ausentes, symlinks, paths inválidos, arquivos não regulares, falhas de leitura e mudanças
observáveis aparecem em `issues`. Qualquer issue torna a cobertura `partial`. Um caminho ausente que
representa a mesma ocorrência física observada em outro caminho do mesmo Asset e raiz é apenas
histórico para fins de cobertura. Se o host não
oferecer o confinamento POSIX exigido, a operação falha fechada com cobertura `unavailable`.

No POSIX, a raiz absoluta é aberta componente por componente e cada diretório/arquivo é aberto
relativamente a descritores com `O_NOFOLLOW`. O arquivo final deve ser regular. Device, inode,
tamanho, mtime, ctime e link count são comparados antes/depois do hashing, e o nome é revalidado
contra o descritor aberto. Tamanho, mtime e `filesystem_id` catalogados, quando presentes, também
devem coincidir. Um SHA-256 catalogado como `verified` divergente torna a localização alterada.

Essas garantias impedem redirecionamento por symlink e detectam alterações observáveis durante a
leitura. Elas não criam snapshot atômico contra todo escritor concorrente; o resultado continua
sendo evidência pontual read-only. A leitura pode atualizar atime ou causar efeitos próprios do
filesystem, driver ou mídia remota.

## Busca e revisão no desktop

Em uma biblioteca aberta, **Ferramentas → Duplicatas exatas → Buscar duplicatas** inicia uma
leitura em segundo plano das localizações já catalogadas. Abrir a tela consulta o resultado
da sessão. Grupos e ocorrências têm paginação vinculada ao mesmo resultado. A interface
mostra miniaturas do catálogo quando disponíveis, raiz, caminho relativo, SHA-256 e
contagem de cópias físicas independentes. O resultado fica em memória e pode ser refeito
com **Buscar novamente**. Ao fechar ou trocar de biblioteca, a interface descarta o resultado
da sessão anterior. Cobertura parcial ou indisponível aparece no resultado, com contagem e
amostra dos impedimentos. Os dados do modo demo permanecem identificados como sintéticos.

O Duplicate Lab confirmou o pré-agrupamento por tamanho antes do hashing integral. O detector
do Photo Manager já aplica essa estratégia e a adapta às identidades e ao confinamento do
catálogo. Similaridade visual, critérios de retenção e quarentena do Lab ficam fora desta entrega.

## Fora de escopo

Persistência do hash no Asset, similaridade visual, decisão de retenção pelo desktop,
quarentena, restauração e mutação física do acervo. Igualdade binária e escolha de preservação não alteram a
identidade lógica: Assets, anotações e todas as FileLocations são preservados.
