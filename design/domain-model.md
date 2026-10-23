# Modelo conceitual candidato

Este modelo é uma hipótese para discussão, não schema de produção.

## Entidades e invariantes

### Asset

Identidade lógica da mídia, independente do caminho. Campos candidatos: `id` (UUID), `kind` (`photo|video`), `content_hash` opcional/verificado, `byte_size`, `media_type`, `capture_time`, `capture_time_source`, `imported_at`, `status`. Um Asset pode ter várias localizações, tags e álbuns. O hash não deve ser a única identidade antes da leitura completa.

### FileLocation

Ocorrência física: `id`, `asset_id`, `root_id`, caminho relativo normalizado, identidade do filesystem quando disponível, tamanho/mtime observados, estado (`present|missing|moved_candidate|offline`), `last_seen_at`. Unique em `(root_id, relative_path)`. Separar localização de Asset permite reconhecer mudança sem trocar a identidade lógica.

### Album e AlbumAsset

`Album` é coleção virtual (`id`, nome, descrição, datas). `AlbumAsset` é associação muitos-para-muitos com `album_id`, `asset_id`, posição opcional e data de inclusão; chave única no par. Nenhum arquivo é movido ao adicionar a álbum.

### Tag e AssetTag

`Tag` possui identidade, nome exibido e chave normalizada única; hierarquia fica adiada. `AssetTag` associa muitos-para-muitos, com origem (`user|imported`), confiança opcional e data. Sinônimos e taxonomia não entram no primeiro incremento.

### Metadata

Valores extraídos e observáveis, separados de anotações do catálogo: `asset_id`, namespace (`exif|xmp|iptc|container|filesystem|sony`), chave, valor tipado/serializado, origem, data de extração e versão do extrator. Para GPS, armazenar acesso/política explícitos e evitar logs. Uma tabela larga com campos frequentes pode coexistir com dados brutos limitados; blobs completos não devem ser copiados sem necessidade.

### ImportSession

Unidade auditável: origem, destino, política, início/fim, estado e resumo. Itens filhos registram caminho de origem, destino planejado, resultado (`copied|skipped|conflict|failed`), checksum/verificação e erro sanitizado. A origem não é apagada por padrão.

### Thumbnail

Cache regenerável: `asset_id`, variante/tamanho, versão do gerador, orientação aplicada, hash/mtime da fonte e caminho do cache. Não é fonte de verdade; ausência apenas causa regeneração.

## Tipos de suporte recomendados

- `LibraryRoot`: raiz observada e sua disponibilidade, evitando caminhos absolutos espalhados.
- `UserAnnotation`: título, descrição, rating 0–5 e favorito, separados do metadata extraído.
- `AuditEvent`: operação explícita, ator, alvo, antes/depois e resultado.
- `ReconciliationObservation`: evidência usada para propor que um arquivo ausente foi movido.

## Relações

```text
Asset 1 ── * FileLocation
Asset 1 ── * Metadata
Asset 1 ── * Thumbnail
Asset * ── * Album  (AlbumAsset)
Asset * ── * Tag    (AssetTag)
ImportSession 1 ── * ImportItem ── 0..1 Asset
Asset 1 ── 0..1 UserAnnotation
```

## Datas e reconciliação

Guardar o instante e sua proveniência: EXIF `DateTimeOriginal`, XMP/container, sidecar, mtime e data informada pelo usuário não são intercambiáveis. `capture_time` é uma projeção escolhida por política, com timezone/offset e precisão quando conhecidos.

Para mudança externa, a reconciliação deve ser conservadora: caminho ausente -> procurar candidatos por identidade do filesystem -> tamanho + hash forte já conhecido -> pedir confirmação quando ambíguo. Nome, mtime ou perceptual hash isolados não autorizam religação.

## SQLite

SQLite é suficiente para uma primeira versão local: transações ACID, foreign keys, índices, FTS5 e backup portátil atendem a um único usuário/processo coordenado. Recomendações:

- habilitar `foreign_keys`, migrações versionadas e testes de upgrade/rollback;
- índices em caminhos, status, capture_time, hash, joins e chaves normalizadas;
- FTS5 para título/descrição/tags, sem depender dele para integridade;
- WAL apenas após testar comportamento em disco local; não manter catálogo ativo em share de rede;
- cache de thumbnails fora do banco, com registros regeneráveis;
- backups consistentes pela API de backup, nunca cópia ingênua durante escrita.

Limites que justificariam reavaliar: múltiplos escritores remotos, colaboração, catálogo em rede ou volume/consultas comprovadamente acima do perfil local. Nada disso faz parte do escopo atual.

