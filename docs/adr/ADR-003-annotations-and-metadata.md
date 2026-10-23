# ADR-003 — Organização, anotações e metadados

- Status: Aceito
- Data: 2026-10-23

## 1. Contexto

O MVP precisa organizar mídia sem mover originais. A Sony documenta labels, títulos, descrições e avaliações, mas álbuns locais não foram comprovados. Para este produto, álbuns e tags são requisitos próprios. XMP aparece no manifesto Sony, porém seu comportamento não foi demonstrado e nenhuma compatibilidade binária será assumida.

## 2. Problema

É preciso modelar coleções e anotações editáveis, persistir localmente e manter clara a fronteira entre fatos extraídos dos arquivos e escolhas do usuário, preparando exportação futura sem escrever nos originais agora.

## 3. Alternativas consideradas

1. **Pastas físicas como álbuns.** Mistura organização lógica com filesystem e exige movimentos.
2. **Gravar tudo imediatamente em EXIF/XMP.** Melhora portabilidade, mas arrisca originais, perde auditabilidade e depende de políticas ainda não definidas.
3. **Tabela genérica chave/valor para tudo.** Flexível, mas enfraquece invariantes de rating, nomes e relações.
4. **Modelo relacional explícito em SQLite, separado da metadata extraída.** Simples, consultável e seguro. É o escolhido.

## 4. Decisão

Álbuns são coleções virtuais do catálogo. `AlbumAsset` implementa a relação muitos-para-muitos, com inclusão idempotente, data de inclusão e posição opcional. Adicionar/remover de álbum não move, copia ou apaga arquivo.

Tags são entidades reutilizáveis. O nome exibido preserva a escolha do usuário; a chave normalizada é calculada por Unicode NFKC, trim das bordas, colapso de whitespace interno e casefold. Acentos não são removidos. A chave normalizada é única. Renomear para chave existente exige mesclagem explícita futura; não ocorre silenciosamente. `AssetTag` é muitos-para-muitos e registra origem e data.

`UserAnnotation` contém por Asset: título opcional, descrição opcional, rating opcional de 1 a 5, favorito booleano, correção temporal opcional definida no ADR-002 e datas de alteração. Rating ausente é `NULL`, nunca zero. Favorito é independente do rating; isso evita reproduzir sem prova a semântica Sony de favorito derivado de avaliação.

`Metadata` contém somente fatos extraídos/observados, com namespace, chave, valor bruto/tipado, fonte e versão do extrator. Anotações nunca são gravadas como se fossem metadata extraída. Conflitos não sobrescrevem fontes.

SQLite é a persistência inicial e autoridade para álbuns, tags e anotações. Foreign keys e unicidade protegem relações. Thumbnails ficam fora do banco e são regeneráveis.

Nenhuma operação desta fase grava nos arquivos originais ou sidecars. Exportação futura para XMP/sidecar será um caso de uso explícito: gera plano/diff, escolhe mapeamento e destino, exige confirmação, escreve de forma atômica e auditável e preserva o valor de catálogo mesmo quando a exportação falhar. Essa exportação não está implementada nem implicitamente habilitada.

## 5. Justificativa

O modelo relacional cobre o MVP sem depender da organização física ou de formatos proprietários. Campos explícitos mantêm regras simples e pesquisáveis. Separar metadata e anotação protege proveniência e permite mudar extratores ou adicionar exportadores sem mudar a intenção do usuário.

## 6. Invariantes

- Álbuns e tags não alteram o filesystem.
- O par `(album_id, asset_id)` é único.
- O par `(asset_id, tag_id)` é único; a associação registra sua origem corrente sem duplicar a relação.
- `Tag.normalized_key` é única; o nome exibido não é destruído pela normalização.
- Rating é `NULL` ou inteiro entre 1 e 5.
- Favorito é booleano independente do rating.
- Há no máximo uma anotação editável corrente por Asset.
- Metadata extraída é distinguível por fonte e nunca é sobrescrita por anotação.
- Original e sidecar não são escritos sem caso de uso futuro explícito e confirmação.
- Falha de exportação futura não perde a anotação do catálogo.

## 7. Consequências

O catálogo é inicialmente a única fonte das anotações, então backup do SQLite é essencial. Outros aplicativos não verão alterações até existir exportação. A normalização evita tags duplicadas por caixa/whitespace, mas mantém diferenças de acentuação. Favoritos podem ser filtrados sem consumir uma estrela específica. Um importador futuro terá de decidir, por política explícita, se anotações externas viram metadata observada ou sugestões de anotação.

## 8. Casos de teste futuros

- incluir o mesmo Asset duas vezes em álbum permanece idempotente;
- remover de álbum não toca na `FileLocation`;
- ` Viagem ` e `viagem` resolvem para a mesma chave, preservando nome exibido escolhido;
- `cafe` e `café` permanecem tags distintas;
- rating aceita 1 e 5, rejeita 0, 6 e frações;
- favorito pode ser verdadeiro com rating nulo;
- editar título não altera metadata extraída de título XMP;
- duas fontes de metadata com a mesma chave permanecem distinguíveis;
- exclusão de thumbnail não afeta anotação;
- plano futuro de exportação falha sem modificar original nem anotação.

## 9. Questões adiadas

- álbuns aninhados, smart albums, ordenação manual e capas;
- hierarquia, aliases, cores e mesclagem de tags;
- histórico/revisões completas de anotações;
- mapeamento de rating/favorito/tags para namespaces XMP;
- política de importação de anotações externas;
- concorrência entre catálogo e sidecar alterado externamente;
- busca FTS e idiomas de tokenização.
