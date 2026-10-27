# Detecção read-only de duplicatas exatas — Duplicate Integration 01A

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

## Cobertura e confinamento

Somente localizações `present`, de tipo `file`, em raízes `available` são elegíveis. Localizações
offline, ausentes, symlinks, paths inválidos, arquivos não regulares, falhas de leitura e mudanças
observáveis aparecem em `issues`; qualquer issue torna a cobertura `partial`. Se o host não
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

## Fora de escopo

Não há scanner ou CLI, persistência de decisão/hash, migração ou índice, similaridade visual,
escolha de preservação, quarentena, restauração, interface ou mutação do catálogo/acervo. Igualdade
binária não altera a identidade lógica: Assets, anotações e todas as FileLocations são preservados.
