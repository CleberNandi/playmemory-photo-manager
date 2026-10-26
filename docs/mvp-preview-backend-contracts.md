# Contratos de backend do MVP Preview 01

## Objetivo e escopo

Esta especificação define a menor fronteira Python de leitura necessária para abrir um catálogo
sintético, preencher uma galeria, consultar detalhes e disponibilizar thumbnails sintéticas a uma
futura interface. Não implementa frontend, Electron/Tauri, API HTTP, decoder, busca completa,
framework de jobs, schema ou código de produção.

O backend permanece independente do shell. SQLite é a autoridade do catálogo; o filesystem é
uma fonte externa observada no momento da leitura. Nenhum contrato abaixo escreve em originais,
associa Assets por hash ou mistura consultas com operações de catalogação.

## Evidência inspecionada

A proposta foi confrontada com ADR-001 a ADR-004, Product UX Discovery 01, jornadas e estados do
MVP, Foundations 02–04C.1, schema `001_initial_schema.sql`, models, repository, `Catalog` e testes.

### Capacidades reutilizáveis

| Capacidade existente | Reuso |
| --- | --- |
| `initialize_database()` e conexão gerenciada | Abrir/migrar catálogo sintético, validar schema, foreign keys e funções Unicode |
| `Catalog.get_asset()` / `list_assets()` | Validação de UUID, erro público e baseline sem joins |
| `get_asset_locations()` e consultas de raiz | Preservar todas as ocorrências e disponibilidade persistida |
| `get_annotation()` e `list_asset_tags()` | Compor detalhes sem alterar anotações |
| Dataclasses `Asset`, `FileLocation`, `LibraryRoot`, `Annotation`, `Tag` | Vocabulário de domínio existente; não duplicar entidades |
| `CatalogRepository` | Padrão de SQL encapsulado e mapeamento; não deve ser exposto à interface |
| Paginação atual, limite 1–100 | Reutilizável em listas administrativas, mas insuficiente para scroll estável da galeria |
| Tabelas `metadata` e `thumbnail` | Persistência já modelada; ainda sem models/casos de uso públicos |
| Scanner read-only | Catalogação e observação de árvores; não é um resolvedor seguro de mídia ou thumbnail |

### Lacunas reais

- `list_assets()` usa `LIMIT/OFFSET`, ordena apenas por UUID e não retorna localização,
  anotação, data projetada ou thumbnail.
- Não há projeções de leitura próprias para card, detalhes, metadata, thumbnail ou estado de
  disponibilidade agregado.
- O model público `Asset` não expõe os campos `captured_*` existentes na tabela.
- Não há consulta pública de `metadata` nem de `thumbnail`; os testes atuais validam o schema por
  SQL direto.
- Não há busca, filtros combináveis, contagem confiável do resultado ou cursor opaco.
- Não há resolução confinada de uma `FileLocation`, abertura de conteúdo, decoder, gerador/cache
  de thumbnail ou tratamento tipado de mudança após catalogação.
- O registro de thumbnail identifica o Asset e um `source_fingerprint`, mas não a FileLocation de
  origem; isso é insuficiente para regeneração auditável quando um Asset tem várias ocorrências.
- Não há infraestrutura de jobs, progresso ou recuperação. A catalogação existente é síncrona.

## Fronteiras propostas

Introduzir, no próximo incremento, uma camada de queries de aplicação, separada de `Catalog` e de
seu repositório de mutação:

```text
futuro adapter do shell
        │ DTOs sem caminhos absolutos
        ▼
GalleryQueries ───────► SQLite catalog (somente leitura)
        │
        ├── AssetMediaResolver ─► raiz configurada (somente leitura)
        └── ThumbnailStore ─────► cache privado/sintético
```

`GalleryQueries` compõe projeções e executa SQL de leitura em transações curtas. Não acessa o
filesystem. `AssetMediaResolver` recebe IDs, relê catálogo e resolve uma ocorrência sob política
de confinamento. `ThumbnailStore` só serve artefatos sob sua raiz privada. Esses contratos Python
podem ser chamados diretamente em testes ou por uma futura ponte local; não exigem HTTP.

## A. Consulta da galeria

### Tipos mínimos

Nomes são ilustrativos; a implementação deve usar dataclasses congeladas e enums, mantendo os
models existentes como entidades do domínio.

```python
GalleryQuery(
    page_size: int,                 # 1..100
    after: str | None,              # cursor opaco e versionado
    kind: AssetKind | None,
    root_id: str | None,
    availability: AvailabilityFilter | None,
)

GalleryPage(
    items: tuple[GalleryItem, ...],
    next_cursor: str | None,
    has_more: bool,
)

GalleryItem(
    asset_id: str,
    kind: AssetKind,
    media_type: str | None,
    byte_size: int | None,
    captured: CaptureProjection | None,
    annotation: AnnotationSummary,
    representative_location: LocationSummary | None,
    location_count: int,
    availability: AssetAvailability,
    thumbnail: ThumbnailReference | None,
)
```

`LocationSummary` contém IDs, nome da raiz, caminho relativo, disponibilidade persistida e a
evidência observada necessária para diagnóstico. O card não recebe caminho absoluto. Detalhes
retornam todas as localizações relevantes, inclusive offline, missing e moved candidate; nenhuma
é descartada porque outra está presente.

### Ordenação e paginação

Para o Preview, a única ordenação obrigatória é `asset.created_at ASC, asset.id ASC`. O ID é o
desempate total e imutável. A consulta usa keyset:

```sql
WHERE (asset.created_at, asset.id) > (?, ?)
ORDER BY asset.created_at, asset.id
LIMIT page_size + 1
```

O cursor codifica versão do contrato, `created_at`, Asset UUID e fingerprint dos filtros; é opaco
para o consumidor e validado integralmente. Não contém SQL nem caminho. Filtro ou versão
divergente produz `invalid_cursor`, nunca reutilização aproximada.

Essa estratégia evita o deslocamento e custo crescente de `OFFSET`. Ela é determinística para um
catálogo sem escrita concorrente, condição do Preview sintético. Não promete snapshot entre
páginas durante mutações: quando houver catalogação concorrente, a UI deverá concluir a página
atual e oferecer refresh; consistência transacional entre uma sessão inteira exigirá decisão
posterior, não um token de “versão” inventado.

A escolha inicial não oferece ordenação por nome ou data de captura. Essas opções dependem de
semântica para múltiplas localizações, valores flutuantes e índices medidos.

### Localização representativa e disponibilidade

A localização representativa serve apenas para preview/abertura, nunca para identidade. Ordem
determinística proposta:

1. arquivo `present` em raiz `available`;
2. localização `offline` ou raiz offline;
3. `moved_candidate`;
4. `missing`;
5. desempate por `library_root_id`, caminho relativo e `FileLocation.id`.

`AssetAvailability` é uma projeção de catálogo: `available`, `offline`, `unavailable` ou
`no_location`. Ela não afirma que o arquivo existe agora. O estado ao vivo só nasce quando o
resolvedor tenta abrir uma localização e pode ser `opened`, `offline`, `not_found`,
`permission_denied`, `changed`, `unsafe_path`, `unsupported` ou `io_error`.

A agregação usa somente o estado persistido: `available` quando existe localização `present` em
raiz `available`; na ausência dela, `offline` quando existe localização `offline` ou pertencente
a raiz offline; na ausência das anteriores, `unavailable` quando resta ao menos uma localização
(`missing` ou `moved_candidate`); e `no_location` quando não existe localização. Uma inconsistência
persistida entre raiz e localização não é corrigida nem promovida por uma consulta de leitura.

### Filtros iniciais

Somente filtros demonstrados pelo Preview:

- `kind` (`photo` ou `video`);
- `root_id`, por associação a ao menos uma FileLocation da raiz;
- disponibilidade agregada persistida.

Sem busca textual, nome, tag, álbum, rating, intervalo temporal ou combinações livres nesta
fase. O filtro por raiz não transforma uma localização em identidade nem oculta as outras nos
detalhes.

## B. Thumbnail

### Referência e variantes

Variantes iniciais propostas: `grid_256` (caixa máxima 256 × 256) e `viewer_1024` (caixa máxima
1024 × 1024), sem upscale. São nomes de contrato, não promessa de formato do arquivo. Uma
thumbnail válida deve estar ligada a:

- Asset UUID;
- FileLocation UUID que forneceu os bytes;
- variante e versão do gerador;
- fingerprint conservador da fonte;
- dimensões de saída e media type do cache.

O fingerprint deve incluir ao menos identidade da localização, tamanho e mtime observados no
descritor aberto; quando uma etapa futura calcular SHA-256 verificado, pode incorporá-lo. Mtime ou
tamanho isolado nunca prova conteúdo inalterado. Como o schema atual não guarda
`source_location_id`, o próximo incremento sintético não deve fingir persistência completa nesse
registro nem sobrecarregar `source_fingerprint` com estrutura opaca.

### Preview sintético

O menor incremento usa thumbnails-fixture pregeradas dentro de uma raiz temporária controlada,
associadas no fixture por Asset UUID e variante. Não adiciona Pillow nem decoder real. Isso testa
consulta, placeholder, cache hit/miss, media type, limites de leitura e confinamento sem afirmar
que geração de thumbnails está pronta.

`ThumbnailStore.open(asset_id, variant)` devolve bytes limitados ou stream/read handle controlado
e um resultado tipado. O frontend recebe um identificador opaco ou bytes pela futura ponte, nunca
`file://` arbitrário ou caminho absoluto.

### Cache e invalidação futura

- cache fora do SQLite e fora das raízes da biblioteca;
- nome derivado de IDs/variante/versão, nunca de caminho fornecido pelo usuário;
- raiz e ancestrais sem symlink; arquivos regulares somente;
- escrita futura por temporário exclusivo, verificação e rename local; nunca no original;
- entrada é válida somente se versão, origem e fingerprint ainda coincidirem;
- cache ausente, obsoleto ou corrompido vira miss regenerável, não indisponibilidade do Asset;
- limites de quantidade/tamanho e política de eviction serão definidos após medição.

### Decoder read-only futuro

Decoder é adapter separado e não faz parte do incremento sintético. Deve abrir um descritor já
confinado, aplicar limites antes/depois da decodificação, normalizar orientação sem salvar o
original, recusar formatos não allowlisted e converter falhas em erros tipados. Imagem
malformada, decompression bomb, dimensão/pixels excessivos, truncamento ou codec ausente não pode
derrubar o processo de queries. Isolamento em worker só será decidido com evidência; não é
presumido agora.

## C. Visualizador e detalhes

```python
AssetDetails(
    asset: AssetSummary,
    capture: CaptureProjection | None,
    annotation: Annotation | None,
    metadata: tuple[MetadataObservation, ...],
    metadata_state: MetadataState,
    locations: tuple[LocationDetails, ...],
)
```

`get_asset_details(asset_id)` valida UUID e retorna uma projeção consistente em uma transação de
leitura. Para o Preview, todas as localizações cabem no contrato com limite explícito de 100; se
houver mais, o resultado deve sinalizar truncamento em vez de ocultá-lo. Metadata não vazia usa
estado `extracted` e preserva a proveniência de cada observação. Metadata vazia usa
`not_extracted`: o schema atual não persiste uma execução de extração vazia ou falha, portanto os
estados futuros `extracted_empty` e `extraction_failed` não podem ser fabricados no primeiro
incremento.

Abrir mídia é uma segunda operação: `open_asset_media(asset_id, location_id | None)`. Sem
`location_id`, o backend reavalia a localização representativa; com ID, confirma que ela pertence
ao Asset. O resultado mantém separado o snapshot persistido e a observação ao vivo. Arquivo
alterado não atualiza catálogo, não troca o Asset e não é aberto como se fosse o original
catalogado; retorna `changed` com diagnóstico sanitizado. Não há edição, rotação persistida,
sidecar ou escrita de metadata.

## D. Metadata e tempo

O schema já representa namespace, chave, origem, chave de origem, valor bruto/interpretado, tipo,
erro de parse, conflito, versão/instante do extrator e semântica temporal. `asset.captured_*`
representa a projeção selecionada; `user_annotation.corrected_*` representa correção manual.

`CaptureProjection` deve expor valor local, precisão, estado de timezone, offset/nome quando
existentes, tipo da fonte, ID da metadata selecionada e motivo. Tempo sem timezone continua
flutuante. Componentes ausentes não são preenchidos; data de importação/criação do registro não
vira captura.

No estado atual, a 04C.1 não extrai metadata nem preenche projeção temporal. Logo, Assets
catalogados normalmente retornam `captured=None` e `metadata_state=not_extracted`. Tabela vazia
não prova que o arquivo não possui EXIF. O primeiro incremento apenas lê fixtures sintéticas já
persistidas; não cria extrator.

## E. Necessidades de jobs

Não criar framework genérico. O contrato futuro mínimo para geração real de thumbnails ou
extração deve informar:

- ID opaco, tipo, escopo e fase;
- `queued`, `running`, `cancelling`, `cancelled`, `completed`, `completed_with_failures`, `failed`
  ou `interrupted`;
- unidades/bytes concluídos e total somente quando conhecido;
- falhas tipadas por item, sanitizadas, sem abortar o lote quando seguro;
- pedido de cancelamento cooperativo e ponto em que o trabalho realmente terminou;
- resumo final suficiente para repetir apenas o que falhou.

O Preview com thumbnails pregeradas não precisa iniciar job. Sem persistência de jobs, reiniciar o
processo não pode prometer retomada: trabalho antes observado como ativo deve reaparecer como
`interrupted` ou ser descartado de modo explícito pelo adapter de sessão. Persistência, retries e
retomada ficam para um caso demonstrado, não para esta especificação.

## Segurança de resolução de mídia

Validar caminho lexical é necessário, mas não suficiente. O scanner não concede ao thumbnail ou
visualizador um descritor seguro reutilizável e sua proteção não é herdada automaticamente.

1. A entrada pública contém somente Asset/FileLocation IDs; o backend busca raiz e relativo no
   catálogo.
2. Rejeitar raiz offline, localização não `present`, entry type diferente de arquivo, caminho
   absoluto, vazio, não canônico, `..`, NUL ou separadores incompatíveis.
3. Nunca aceitar caminho absoluto vindo do frontend nem concatenar e confiar em `resolve()`.
4. Em POSIX, abrir raiz e cada componente relativo com primitivas descriptor-relative e
   `O_NOFOLLOW`; conferir tipo e identidade no descritor. Verificar `fstat` antes e depois da
   leitura contra tamanho/mtime/file-id persistidos quando disponíveis.
5. Fechar descritores em toda saída. Limitar bytes, dimensões, pixels, tempo e concorrência.
6. Em plataformas sem garantias equivalentes, o adapter deve declarar capacidade reduzida e
   falhar fechado para geração/leitura não segura; uma política Windows precisa de PoC própria.
7. Cache tem raiz distinta, conferida contra symlinks, e só serve arquivo regular allowlisted.
8. Erros públicos não incluem caminho absoluto, stack trace, bytes de metadata privada ou GPS.

Essas medidas reduzem traversal e symlink swap, mas não prometem snapshot atômico contra escritor
local adversarial. Alteração detectável resulta em `changed`; nenhuma observação atual é
persistida por um contrato de leitura.

## Impacto no schema

Nenhuma migração é necessária para o próximo incremento sintético. Consultas podem ler as tabelas
atuais, e thumbnails-fixture podem viver em diretório temporário com manifesto de teste.

Antes de persistir thumbnails reais, revisar uma migração separada para ligar explicitamente o
registro à FileLocation de origem e definir o fingerprint como campos versionados, não texto
opaco. Índices para keyset/filtros devem ser propostos somente após `EXPLAIN QUERY PLAN` e medições;
o índice atual por captura e os índices de FileLocation podem ajudar, mas não cobrem toda a
projeção. Este documento não autoriza modificar schema.

## Estratégia de testes

- banco e árvores/cache exclusivamente temporários e sintéticos;
- testes unitários de cursor: assinatura estrutural, versão/filtros, limite e cursor adulterado;
- paginação com timestamps iguais, UUIDs distintos, página vazia e `limit + 1`;
- Asset sem localização, múltiplas localizações, raiz offline, missing e desempate determinístico;
- detalhes com/sem anotação, metadata temporal flutuante, conflito e `not_extracted`;
- nenhum caminho absoluto em DTOs ou erros públicos;
- cache hit/miss, variante inválida, arquivo grande, não regular, symlink e traversal;
- troca de componente por symlink entre validação e abertura, coberta no adapter POSIX;
- arquivo removido, permissão negada, tamanho/mtime/file-id divergente e mudança durante leitura;
- testes de contrato sem React/Electron e sem rede;
- `EXPLAIN QUERY PLAN` documentado para o corpus sintético antes de qualquer índice novo.

## Primeiro incremento implementável

1. Criar módulo de queries read-only com `GalleryQuery`, `GalleryPage`, `GalleryItem` e
   `AssetDetails`.
2. Implementar keyset por `(created_at, id)`, os três filtros iniciais e composição de
   localizações/anotação/projeção temporal.
3. Criar um resolvedor de thumbnail sintética limitado a cache temporário, por Asset UUID e
   variante, sem decoder ou acesso a originais.
4. Expor erros tipados e sanitizados para catálogo incompatível, Asset ausente, cursor inválido,
   thumbnail ausente/corrompida e localização indisponível.
5. Testar tudo pela API Python, sem shell, HTTP ou frontend.

### Critérios de aceite verificáveis

- catálogo sintético abre pela fábrica gerenciada e schema incompatível falha sem ser recriado;
- duas ou mais páginas retornam cada Asset exatamente uma vez, em ordem total, sem `OFFSET`;
- filtros por tipo, raiz e disponibilidade não alteram a identidade ou escondem localizações nos
  detalhes;
- detalhes retornam Asset, projeção temporal honesta, anotação e todas as localizações até o
  limite declarado, com truncamento explícito;
- ausência de metadata é `not_extracted`, sem data artificial;
- thumbnail sintética válida é servida somente da raiz de cache; traversal, caminho absoluto,
  symlink, variante desconhecida e arquivo excessivo falham fechados;
- nenhum DTO destinado à interface contém caminho absoluto ou conexão/row SQLite;
- consultas não escrevem no catálogo nem no acervo; teste compara `total_changes`, conteúdo do
  banco e árvore original antes/depois;
- erros distinguem indisponibilidade, ausência, mudança, entrada insegura e falha de I/O sem
  vazar caminho absoluto;
- testes existentes continuam aprovados e os novos executam sem Electron e sem rede.

## Decisões pendentes

- política segura e portátil de abertura no Windows;
- decoder, formatos allowlisted, limites de pixels/memória e eventual isolamento;
- schema e lifecycle de thumbnails reais;
- consistência de paginação durante catalogação concorrente;
- ordenação por data/nome e índices após medição;
- extração de metadata e persistência de estado de job;
- forma da ponte local do shell, que não precisa nem deve ser decidida como HTTP agora.
