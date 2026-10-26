# Gallery read model — MVP Preview 02

## Escopo

`playmemories_photo_manager.gallery` é a API Python read-only para a galeria e os detalhes de
Asset. Ela usa uma conexão SQLite gerenciada já aberta, não executa scanner, não acessa originais,
não extrai metadata e não cria thumbnails. As projeções públicas são dataclasses congeladas e não
expõem conexão, `sqlite3.Row` nem caminho absoluto de `LibraryRoot`.

## API pública

- `GalleryQueries(connection).list_assets(GalleryQuery(...)) -> GalleryPage`;
- `GalleryQueries(connection).get_asset_details(asset_id) -> AssetDetails`;
- `SyntheticThumbnailStore(cache_root, fixtures).get_reference(asset_id, variant)`;
- `SyntheticThumbnailStore.open(thumbnail_id) -> ThumbnailContent`.

Um `SyntheticThumbnailStore` opcional pode ser passado ao construtor de `GalleryQueries`; nesse
caso, cards com fixture `grid_256` recebem somente a referência opaca, sem abrir o arquivo.

Exemplo de paginação:

```python
from playmemories_photo_manager.catalog import initialize_database
from playmemories_photo_manager.gallery import GalleryQueries, GalleryQuery

connection = initialize_database("catalog.sqlite3")
queries = GalleryQueries(connection)

page = queries.list_assets(GalleryQuery(page_size=50))
for item in page.items:
    print(item.asset_id, item.availability)

if page.next_cursor is not None:
    next_page = queries.list_assets(GalleryQuery(page_size=50, after=page.next_cursor))

details = queries.get_asset_details(page.items[0].asset_id)
connection.close()
```

O limite aceito é de 1 a 100. O cursor é base64url opaco, canônico e versionado; contém apenas a
chave `(asset.created_at, asset.id)`, a versão e fingerprints estruturais. Ele não contém SQL nem
caminhos. Alteração, versão desconhecida ou uso com filtros diferentes resulta em
`InvalidCursorError`. A navegação usa exclusivamente keyset e `LIMIT page_size + 1`, sem
`LIMIT/OFFSET`.

Cada chamada lê uma projeção consistente em uma transação curta. Uma sequência de páginas não é
um snapshot transacional único: inserções ou alterações concorrentes podem mudar o resultado e o
consumidor deve oferecer refresh.

## Projeções e localizações

A ordenação é `asset.created_at ASC, asset.id ASC`. Assets com o mesmo SHA-256 permanecem linhas e
identidades distintas. O card traz uma localização representativa, mas detalhes trazem todas as
localizações até o limite explícito de 100 e sinalizam `locations_truncated`.

A escolha representativa é determinística: arquivo `present` em raiz `available`; depois estado
offline; `moved_candidate`; `missing`; e, por fim, desempate por raiz, caminho relativo e ID. A
disponibilidade é sempre uma projeção dos estados persistidos. A query não verifica existência no
filesystem nem persiste uma observação física atual.

`CaptureProjection` preserva valor local, precisão, timezone/offset, fonte, metadata selecionada e
motivo. Tabela de metadata vazia produz `not_extracted`, não “sem metadata na fotografia”. Quando
existem observações, o estado é `extracted` e cada observação preserva sua proveniência. Anotação e
tags existentes são expostas sem alterar as entidades de domínio.

## Plano de consulta e índices

`EXPLAIN QUERY PLAN` foi executado sobre o schema atual e um catálogo sintético. SQLite usa
`ix_file_location_asset` nas subconsultas por Asset e a PK de `library_root` no join. Para a ordem
principal, o plano mostrou `SCAN a` e `USE TEMP B-TREE FOR ORDER BY`, pois não existe índice em
`(asset.created_at, asset.id)`. Nenhum índice ou migração foi criado automaticamente, conforme o
limite deste incremento. Esse custo permanece risco a medir no corpus sintético de 50 mil Assets;
uma eventual migração deve ser proposta separadamente com medições.

## Thumbnails sintéticas

O store aceita somente um manifesto de fixtures pregeradas com UUIDs canônicos, variante
allowlisted, media type allowlisted e nome simples de cache. O chamador abre a fixture por ID
opaco; nenhum path público é aceito. Em POSIX, raiz e ancestrais são verificados com `lstat`, a
raiz e o arquivo são abertos por descritor com `O_NOFOLLOW`, somente arquivo regular é aceito e a
leitura tem limite de bytes e verificação antes/depois. Traversal, links simbólicos, arquivo
ausente, entrada grande ou confinamento não demonstrável falham fechados.

O store não escreve. Cache e acervo são raízes distintas, e não há decoder, geração, invalidação,
eviction ou persistência completa do vínculo com `FileLocation`. A implementação não promete
garantias equivalentes no Windows: nessa plataforma, falha com
`UnsupportedThumbnailPlatformError` até existir uma PoC específica.

Exemplo sintético:

```python
from playmemories_photo_manager.gallery import (
    SyntheticThumbnailFixture,
    SyntheticThumbnailStore,
    ThumbnailVariant,
)

fixture = SyntheticThumbnailFixture(
    id="00000000-0000-0000-0000-000000000002",
    asset_id="00000000-0000-0000-0000-000000000001",
    variant=ThumbnailVariant.GRID_256,
    cache_name="fixture.png",
    media_type="image/png",
)
store = SyntheticThumbnailStore("/tmp/private-preview-cache", (fixture,))
reference = store.get_reference(fixture.asset_id, fixture.variant)
content = store.open(reference.id)
```

## Próximos contratos necessários à interface

Ainda são necessários: lifecycle seguro de catálogo; ponte local do shell; resolução confinada e
tipada de mídia; decoder read-only; geração/invalidação real de thumbnails; extração de metadata;
jobs com progresso/cancelamento; busca e filtros adicionais; e política medida de índices. Nada
disso é iniciado por este incremento.
