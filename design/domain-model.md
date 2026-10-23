# Modelo conceitual da Foundation 01

Este é o modelo conceitual aprovado pelos ADRs da Foundation 01. Ele define invariantes, não um schema físico de produção.

## Entidades e invariantes

### Asset

Identidade lógica da mídia, independente do caminho. Campos conceituais: UUID aleatório e imutável, `kind` (`photo|video`), hash opcional com estado de verificação, tamanho, media type, projeção temporal selecionada e status. Um Asset pode ter várias localizações, tags e álbuns. SHA-256 é evidência de conteúdo, nunca a identidade lógica e nunca causa fusão automática.

### FileLocation

Ocorrência física: `id`, `asset_id`, `root_id`, caminho relativo normalizado, tipo de entrada, identidade do filesystem quando disponível, tamanho/mtime observados, estado (`present|missing|moved_candidate|offline`) e `last_seen_at`. Unique em `(root_id, relative_path)` para localizações ativas. Separar localização de Asset permite reconhecer mudança sem trocar a identidade lógica. Hardlinks podem ser várias localizações do mesmo Asset; symlinks não são seguidos por padrão.

### Album e AlbumAsset

`Album` é coleção virtual (`id`, nome, descrição, datas). `AlbumAsset` é associação muitos-para-muitos com `album_id`, `asset_id`, posição opcional e data de inclusão; chave única no par. Nenhum arquivo é movido ao adicionar a álbum.

### Tag e AssetTag

`Tag` possui identidade, nome exibido e chave única normalizada por NFKC, trim, whitespace colapsado e casefold, sem remoção de acentos. `AssetTag` associa muitos-para-muitos, com origem e data. Sinônimos, hierarquia e taxonomia ficam adiados.

### Metadata

Valores extraídos e observáveis, separados de anotações: `asset_id`, namespace (`exif|xmp|iptc|container|filesystem|sony`), chave, valores bruto e tipado, origem, precisão/timezone quando temporal, data de extração e versão do extrator. Para GPS, armazenar acesso/política explícitos e evitar logs. Blobs completos não devem ser copiados sem necessidade.

### ImportSession

Unidade auditável: origem, destino, política, início/fim, estado e resumo. Itens filhos registram caminho de origem, destino planejado, resultado (`copied|skipped|conflict|failed`), checksum/verificação e erro sanitizado. A origem não é apagada por padrão.

### Thumbnail

Cache regenerável: `asset_id`, variante/tamanho, versão do gerador, orientação aplicada, hash/mtime da fonte e caminho do cache. Não é fonte de verdade; ausência apenas causa regeneração.

## Entidades de suporte exigidas por invariantes

- `LibraryRoot`: raiz observada e sua disponibilidade, necessária para distinguir `offline` de `missing` e evitar caminhos absolutos espalhados.
- `UserAnnotation`: título, descrição, rating nulo ou 1–5, favorito independente e correção temporal, sempre separados de metadata extraída.
- `ImportItem`: item subordinado à sessão, necessário para retomada e resultado auditável por arquivo.

`AuditEvent` e uma entidade própria de `ReconciliationObservation` ficam adiados; a primeira implementação pode registrar evidências de reconciliação junto à localização/caso de uso sem antecipar um modelo genérico.

## Relações

```text
Asset 1 ── * FileLocation
Asset 1 ── * Metadata
Asset 1 ── * Thumbnail
Asset * ── * Album  (AlbumAsset)
Asset * ── * Tag    (AssetTag)
ImportSession 1 ── * ImportItem ── 0..1 Asset
Asset 1 ── 0..1 UserAnnotation
LibraryRoot 1 ── * FileLocation
```

## Datas e reconciliação

Guardar cada valor e sua proveniência: EXIF `DateTimeOriginal`, XMP/sidecar, container, mtime, importação e correção do usuário não são intercambiáveis. A data de captura no Asset é projeção escolhida pela política do ADR-002, aponta para a fonte e mantém timezone/offset e precisão quando conhecidos. Tempo sem timezone permanece local/flutuante e não é convertido para UTC.

Para mudança externa, a reconciliação é conservadora: file-id estável na mesma raiz, desaparecimento do caminho anterior no mesmo ciclo e atributos compatíveis podem preservar automaticamente a localização; tamanho + SHA-256 verificado produz apenas candidato para confirmação. Nome, mtime, metadata ou hash perceptual isolados não autorizam religação. Conteúdo idêntico em caminhos distintos cria Assets distintos por padrão.

## SQLite

SQLite é suficiente para uma primeira versão local: transações ACID, foreign keys, índices, FTS5 e backup portátil atendem a um único usuário/processo coordenado. Recomendações:

- habilitar `foreign_keys`, migrações versionadas e testes de upgrade/rollback;
- índices em caminhos, status, capture_time, hash, joins e chaves normalizadas;
- FTS5 para título/descrição/tags, sem depender dele para integridade;
- WAL apenas após testar comportamento em disco local; não manter catálogo ativo em share de rede;
- cache de thumbnails fora do banco, com registros regeneráveis;
- backups consistentes pela API de backup, nunca cópia ingênua durante escrita.

Limites que justificariam reavaliar: múltiplos escritores remotos, colaboração, catálogo em rede ou volume/consultas comprovadamente acima do perfil local. Nada disso faz parte do escopo atual.

