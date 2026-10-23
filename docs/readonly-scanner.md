# Scanner read-only — Foundation 04A

## Escopo

A Foundation 04A fornece observação local sequencial de uma raiz explicitamente informada. O
scanner enumera entradas e devolve evidências imutáveis; não importa o catálogo, não abre SQLite,
não cria Assets ou localizações e não faz hashing, reconciliação ou inferência de ausência.

API pública:

```python
from playmemories_photo_manager.scanner import ScanOptions, scan

result = scan("/tmp/synthetic-media", ScanOptions(recursive=True))
for entry in result.entries:
    print(entry.relative_path, entry.entry_type, entry.byte_size)
```

O exemplo pressupõe uma árvore sintética criada pelo chamador. A função não cria a raiz.

## Contratos

`ScanResult` contém:

- UUID aleatório da execução, início e término em UTC;
- `RootObservation` com caminho declarado, caminho absoluto lexical e identidade física quando
  informada pelo host;
- `ScanScope`, que registra caminho relativo inicial, recursividade e que links não foram seguidos;
- diretórios cuja enumeração de nomes terminou, em `covered_directories`;
- tupla ordenada de `EntryObservation` e tupla de `ObservationFailure`;
- `ScanStatus`, que expressa a completude global.

Cada entrada usa caminho relativo com `/` e preserva o texto fornecido pelo filesystem, sem NFKC,
casefold ou tentativa de equivalência. O tipo é `file`, `directory`, `symlink`, `reparse_point` ou
`other`. Tamanho só é informado para arquivo regular. Timestamps brutos podem ser `None`; `ctime`
tem semântica dependente da plataforma e aparece como `changed_ns`, sem ser chamado de criação.

`PhysicalIdentity(device, file_id)` preserva `st_dev` e `st_ino` quando utilizáveis. É uma
observação pontual, possivelmente indisponível ou reutilizável, e não uma identidade lógica ou
portátil. Toda entrada produzida nesta fase é `direct_observation`. O enum também reserva
`unconfirmed_inference` para deixar explícita a distinção, mas o scanner nunca o emite.

## Completude

| Status | Significado |
|---|---|
| `complete` | Todo o escopo solicitado foi enumerado sem falha de cobertura |
| `partial` | Há observações válidas, mas ao menos uma área ou entrada não pôde ser observada |
| `cancelled` | O callback pediu interrupção; observações anteriores são preservadas |
| `root_unavailable` | A raiz não existe, não é diretório, é link, desapareceu ou não pode ser acessada |
| `failed` | A raiz foi identificada, mas uma falha total de I/O impediu sua enumeração |

Falhas registram caminho relativo quando existente, operação, categoria, código do sistema quando
disponível e se comprometem cobertura. Permissão negada, desaparecimento e erro de enumeração não
são convertidos em diretório vazio. O resultado não afirma que qualquer caminho está `missing`.

## Garantias de segurança

- Usa somente operações de consulta (`lstat`, `scandir`, `DirEntry.stat` e classificação de tipo).
- Não abre conteúdo, calcula hash, cria sidecar/thumbnail, muda permissões, move ou exclui entrada.
- Usa `follow_symlinks=False`; symlinks, junctions e reparse points observados não são percorridos.
- Uma raiz que seja symlink é rejeitada, impedindo redirecionamento implícito do escopo.
- Não há dependência ou chamada para a camada de catálogo.
- A ordem é determinística pela ordenação textual dos nomes retornados pelo host.

Read-only descreve a intenção e as chamadas do scanner, não ausência absoluta de efeitos do
filesystem. Enumeração e consulta podem atualizar atime de diretório ou acionar efeitos próprios
de filesystem, driver, antivírus, mídia remota ou sistema operacional.

## Portabilidade e TOCTOU

O scanner converte apenas separadores do caminho relativo para `/`. Não universaliza caixa,
Unicode, volumes ou IDs físicos. `st_dev`/`st_ino`, permissões, `ctime`, symlinks, junctions e
reparse points possuem disponibilidade e semântica diferentes em Linux e Windows.

Cada resultado é um conjunto de observações em instantes próximos, não um snapshot atômico. Uma
entrada pode mudar entre `scandir` e `stat`, ou imediatamente após a observação. Desaparecimento
detectado torna o resultado parcial; alterações não detectáveis nesse intervalo continuam sendo
uma limitação. A 04A não abre descritores de conteúdo nem promete estabilidade para hashing.

## Integração futura com 04B

A etapa seguinte poderá consumir `ScanResult` para avaliar evidências, mas deverá manter uma
fronteira explícita: somente resultados completos podem contribuir para uma decisão de ausência;
identidade física isolada não prova continuidade; igualdade de conteúdo não prova identidade; e
nenhuma transição deve ocorrer sem caso de uso transacional próprio. A 04A não implementa nem
antecipa essas mutações.
