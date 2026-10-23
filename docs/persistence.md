# Arquitetura da persistência — Foundation 02

## Escopo e decisões

O catálogo é um adapter SQLite local e explícito, sem ORM. `database.connect()` é a única
fábrica de conexão operacional: usa autocommit consciente, habilita `PRAGMA foreign_keys = ON`,
confirma que a opção entrou em vigor e registra a função determinística `normalize_tag`. As
tabelas são `STRICT`; a versão mínima efetiva do SQLite é, portanto, 3.37.0.

Esta fundação não acessa filesystem ou mídia, não gera thumbnails, não extrai metadata e não
reconcilia localizações. Caminhos, datas e hashes são fatos fornecidos por futuros casos de uso.

## Modelo físico

| Tabela | Identidade e semântica | Exclusão |
|---|---|---|
| `asset` | UUID interno; tipo, SHA-256 opcional não único e projeção temporal derivada | bloqueada por localização; associações organizacionais/cache são cascata |
| `library_root` | UUID e caminho normalizado globalmente único; `available` ou `offline` | `RESTRICT` enquanto houver localização |
| `file_location` | UUID; Asset + raiz + caminho relativo normalizado; ocorrência física | FKs `RESTRICT`, para não apagar evidência física por acidente |
| `album` | UUID, nome, descrição e datas | cascata somente para `album_asset` |
| `album_asset` | PK composta `(album_id, asset_id)`, data e posição opcional | cascata da entidade removida; nunca toca em arquivo/localização |
| `tag` | UUID, nome exibido e chave Unicode normalizada única | cascata somente para `asset_tag` |
| `asset_tag` | PK composta `(asset_id, tag_id)`, origem e data | cascata da entidade removida |
| `user_annotation` | PK/FK `asset_id`; uma anotação corrente por Asset | cascata com Asset |
| `metadata` | UUID; fato bruto/interpretado, origem, extrator e semântica temporal | cascata com Asset, salvo se selecionada pela projeção (`RESTRICT`) |
| `thumbnail` | UUID; variante, dimensões, versão, fingerprint e caminho de cache | cascata com Asset; não contém BLOB |
| `schema_migration` | versão, nome, SHA-256 do SQL e instante aplicado | gerenciada somente pelo executor |

`Metadata` é criada antes de `Asset` no SQL para permitir a referência circular declarativa:
metadata pertence ao Asset, enquanto a projeção de captura do Asset pode apontar para metadata.
A FK composta `(captured_metadata_id, asset.id) -> (metadata.id, metadata.asset_id)` garante que
a fonte selecionada pertence ao mesmo Asset. Inserções começam com Asset sem projeção, adicionam
observações e então atualizam a projeção.

## Integridade e índices

O banco garante UUIDs canônicos por função determinística, imutabilidade de `Asset.id` por um
gatilho mínimo, enums e booleanos por `CHECK`, rating `NULL` ou inteiro de 1 a 5, tamanhos não
negativos, SHA-256 hexadecimal minúsculo, coerência entre hash e estado, coerência entre valor
temporal/precisão/timezone, uma anotação por Asset e unicidade das associações. Offset explícito
é guardado em minutos entre -840 e +840; tempo sem offset usa `timezone_state = 'unknown'` e não
ganha UTC inventado.

A chave de tag é `NFKC -> split/join de whitespace -> casefold`, preservando acentos. A camada
Python calcula a chave e a constraint `normalize_tag(display_name) = normalized_key` a verifica.
Isso evita depender do `NOCASE` ASCII do SQLite. Escritas em `tag` exigem uma conexão gerenciada,
pois SQLite não oferece NFKC/casefold Unicode nativos.

Índices existem apenas para joins inversos e consultas já previstas: localizações por Asset,
raiz/estado e file-id; Assets por hash e captura; metadata por Asset/chave e conflitos; membros
por Asset/tag; thumbnails por Asset. O índice parcial único de localização cobre
`(library_root_id, normalized_relative_path)` quando o estado não é `missing`. Assim, uma raiz
offline preserva a ocupação do caminho, enquanto observações históricas missing não impedem uma
nova localização ativa.

## Garantias da aplicação

SQLite não normaliza caminhos de forma portável nem gera UUIDs aleatórios. Os futuros casos de
uso devem gerar UUID v4 canônico, normalizar a raiz conforme a plataforma,
armazenar caminhos relativos em forma lexical canônica e rejeitar `..`, escapes e symlinks fora
da raiz. Também devem manter coerência cruzada entre `library_root.availability` e
`file_location.availability`: raiz offline implica localização offline; `missing` só pode resultar
de varredura bem-sucedida de raiz disponível. A persistência representa essa distinção sem
presumir uma varredura.

Correção temporal manual vive em `user_annotation`; a projeção usa
`captured_source_kind = 'manual'`. A aplicação garante que exista correção ativa no mesmo Asset.
Nenhum gatilho complexo foi introduzido apenas para antecipar casos de uso ainda inexistentes.

## Migrações

Arquivos seguem `NNN_nome.sql`, começam em 1 e precisam ser contíguos. Para cada migração, o
executor calcula SHA-256, separa statements completos com o parser do SQLite e os executa sob
um `BEGIN IMMEDIATE` controlado pelo runner. Controle transacional dentro do arquivo é negado;
isso impede `COMMIT` prematuro de escapar da atomicidade. DDL/DML, registro em
`schema_migration` e atualização de `PRAGMA user_version` são confirmados juntos. Em erro, o
runner executa rollback explícito; schema, histórico e `user_version` avançam juntos ou não
avançam.

Na abertura, o executor rejeita: versão maior que a suportada, lacunas/nomes desconhecidos,
histórico divergente de `user_version` e checksum aplicado diferente do SQL versionado. Reabrir
um banco atualizado não reaplica nada. Migrações reversas não são oferecidas; upgrade deve usar
backup consistente e migração aditiva revisada.

## Limitações conhecidas

- Não há scanner, importação, reconciliação, extração, geração de thumbnails ou exportação.
- Não há histórico completo de caminhos/anotações nem modelo de versões de mídia.
- Não há ordenação global definida entre tempo flutuante e instante absoluto.
- O caminho do thumbnail referencia cache externo regenerável; sua gestão virá depois.
- A camada de casos de uso para criação de todas as entidades ainda não existe; somente conexão,
  migração e operação segura de tags fazem parte desta fundação.
- Escritas e `PRAGMA integrity_check` devem usar a conexão gerenciada: conexões SQLite puras não
  conhecem as funções `is_uuid` e `normalize_tag` referenciadas pelas constraints do schema.
- A normalização segue a base Unicode fornecida pelo runtime Python; uma atualização dessa base
  deve ser tratada como mudança de compatibilidade e validada antes de editar tags existentes.
- Concorrência remota, catálogo em share de rede e múltiplos escritores não são suportados.
