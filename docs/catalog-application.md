# Camada de aplicação do catálogo — Foundation 03

## Organização

`Catalog` é a fachada de casos de uso. Ela recebe uma conexão criada por
`initialize_database()`, valida entradas, abre transações de escrita e converte falhas esperadas
em erros estáveis. A conexão continua pertencendo ao chamador e deve ser fechada por ele.

- `models.py`: enums e dataclasses imutáveis retornadas ao chamador;
- `errors.py`: erros públicos, independentes de SQLite ou frameworks;
- `repository.py`: SQL do catálogo e conversão de linhas para contratos;
- `service.py`: validação, invariantes, casos de uso e fronteiras transacionais;
- `database.py`: conexão gerenciada, UDFs e migrações da Foundation 02.

Não há interfaces abstratas de repositório porque existe somente uma implementação real.

## Casos de uso

- Asset: criar, consultar, listar e listar suas localizações;
- LibraryRoot: registrar, consultar e listar;
- FileLocation: registrar, consultar, listar por Asset e listar por raiz;
- Album: criar, consultar, listar, adicionar/remover Asset e listar membros;
- Tag: criar, consultar, listar, associar/remover de Asset e listar por Asset;
- Annotation: consultar e definir separadamente rating, favorito, título e descrição.

O UUID de Asset é gerado pela aplicação. Caminho, SHA-256 e `filesystem_id` nunca selecionam ou
fundem Assets. `create_asset` aceita hash somente como `unverified`; promover um SHA-256 a
`verified` exigirá uma operação futura que represente a leitura integral bem-sucedida. A
associação de álbum é idempotente: retorna `True` quando criada e `False` quando já existia.
Associação duplicada de tag produz `DuplicateAssociationError`. Remoções de associação retornam
se uma linha foi removida; não removem entidades nem mídia.

Cada setter de anotação modifica exatamente um campo. Passar `None` para rating, título ou
descrição é limpeza explícita; campos não mencionados são preservados. Favorito é booleano e
independente do rating. Metadata extraída não participa dessas escritas.

## Contratos e erros

Os valores retornados são dataclasses congeladas e enums baseados em string. Os erros públicos
são subclasses de `CatalogError`:

- `InvalidInputError`: tipo, UUID, enum, paginação ou valor inválido;
- `NotFoundError`: entidade consultada não existe;
- `InvalidReferenceError`: escrita aponta para entidade inexistente;
- `DuplicateAssociationError`: associação não idempotente já existe;
- `UniquenessConflictError`: caminho ativo, raiz ou tag normalizada já existe;
- `InvariantViolationError`: operação válida isoladamente, mas incompatível com o estado atual;
- `PersistenceError`: falha SQLite inesperada, encadeada como causa para diagnóstico.

Mensagens SQLite não são o contrato público. A exceção original permanece em `__cause__` para
debug local e não deve ser apresentada diretamente ao usuário.

## Transações

Cada caso de uso de escrita usa `BEGIN IMMEDIATE`, commit único e rollback para qualquer falha.
Consultas de referência e a mutação pertencem à mesma transação quando formam uma operação
composta. Transações aninhadas e conexão compartilhada entre threads não são suportadas. A
conexão gerenciada é obrigatória para foreign keys e para `is_uuid`/`normalize_tag`.

## Paginação

Listagens usam `limit` e `offset`, ordenação determinística por UUID, tamanho padrão 50 e máximo
100. Limite menor que 1, maior que 100 ou offset negativo são rejeitados. A paginação por offset
é simples e adequada ao catálogo local atual, mas pode repetir ou omitir itens se outra operação
escrever entre páginas; cursores estáveis ficam adiados até existir necessidade comprovada.
Listas sem resultados retornam `[]`.

## Disponibilidade e evidência

Estados de raiz:

- `available`: o chamador declara que a raiz estava acessível no contexto da observação;
- `offline`: a raiz/volume estava indisponível; não significa arquivo ausente.

Estados de localização:

- `present`: ocorrência observada no caminho informado;
- `offline`: última ocorrência conhecida está em raiz atualmente offline;
- `missing`: uma varredura bem-sucedida de raiz disponível não encontrou a ocorrência;
- `moved_candidate`: evidências sugerem movimento, ainda sem reconciliação confirmada.

O registro exige `last_seen_at`: esse valor é um atestado fornecido pelo chamador, não produzido
ou verificado pela camada. A criação pública aceita somente `present` em raiz disponível ou
`offline` em raiz offline. `missing` e `moved_candidate` são estados persistíveis no modelo, mas
não podem ser declarados por `register_location`: exigem evidência de varredura ou reconciliação
que esta fundação deliberadamente não representa. Não existe API para transição posterior;
scanner/reconciliador deverá fornecer evidências e uma política aprovada antes dessa operação ser
adicionada. O caminho relativo é lexical, canônico em sintaxe POSIX e não pode ser absoluto nem
conter `..`; nenhum caminho é resolvido no filesystem.

## Fora do escopo

Não são implementados scanner, monitoramento de volumes, reconciliação, deduplicação, merge,
exclusão de Asset, leitura/escrita de mídia, EXIF/XMP/sidecar, extração de metadata, thumbnails,
busca textual, UI, HTTP, importação ou atualização automática de disponibilidade. Também não há
renomeação de tags, atualização administrativa de raízes ou histórico completo de caminhos;
suas políticas ainda não estão suficientemente definidas.
