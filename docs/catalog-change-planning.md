# Planejamento conservador de mudanças do catálogo — Foundation 04B.2

## Escopo e fronteira

A Foundation 04B.2 compara uma `EvidenceAssessment` já validada com um retrato lógico, explícito
e limitado do catálogo. `plan_changes()` é uma função pura: não abre SQLite, não consulta o
filesystem, não usa relógio, não calcula hash e não gera UUID. Sua saída é uma proposta
diagnóstica imutável, nunca uma autorização de escrita.

O fluxo permanece:

`Scanner → Evidence Evaluator → Change Planner → aplicador transacional futuro`

O aplicador não faz parte desta fundação. O planner não cria ou exclui Assets, não registra ou
altera `FileLocation`, não atualiza `last_seen_at`, não reconcilia movimentos, não funde Assets e
não produz transição para `missing`.

## API e entradas

```python
from playmemories_photo_manager.change_planning import plan_changes

plan = plan_changes(assessment, catalog_snapshot, context)
```

`EvidenceAssessment` preserva o `run_id`, a raiz observada e o `ScanScope` da execução, além de
cobertura, validação estrutural, observações aceitas, informações inconclusivas e impedimentos.
Isso mantém a proveniência da execução do scanner na fronteira de comparação.

`CatalogSnapshot` representa uma leitura lógica de uma única `LibraryRoot` e contém:

- a `LibraryRoot` persistente;
- somente os `Asset` e `FileLocation` relevantes para o escopo consultado;
- o `ScanScope` efetivamente consultado;
- evidências físicas tipadas por identificador de localização, quando disponíveis;
- uma versão ou marcador de leitura opcional fornecido pelo adapter que fez a consulta.

O contrato reutiliza as entidades imutáveis da camada de catálogo, mas o planner revalida em
runtime os campos relevantes e as coerências do schema; não confia apenas em `frozen=True` nem em
snapshots montados manualmente. `LocationPhysicalEvidence`
apenas torna comparável o par `(device, file_id)` quando essa evidência foi previamente registrada
com semântica compatível; o campo legado e opaco `FileLocation.filesystem_id` não é interpretado.
O chamador não deve carregar o catálogo inteiro: deve consultar a raiz e o escopo necessários e
montar um snapshot autocontido. `read_version` é rastreabilidade, não promessa de snapshot
atômico ou isolamento que o adapter não tenha fornecido. Versão ausente ou vazia deixa o plano
inconclusivo, pois um aplicador futuro não teria marcador confiável para revalidação.

`PlanningContext` liga explicitamente o ID e o caminho configurado da raiz ao caminho absoluto
observado, ao escopo e, quando conhecida, à identidade física da raiz. O planner confere esses
valores contra avaliação e snapshot; não aceita equivalência por nome parecido.

## Saída e classificações

`CatalogChangePlan` é uma dataclass congelada com status, itens ordenados, diagnósticos, versão de
leitura e referências de execução/raiz/escopo. Seus campos
`authorizes_catalog_mutation` e `permits_absence_conclusions` são sempre falsos nesta fundação e
não são parâmetros aceitos pelo construtor.

- `known_location_observed`: arquivo diretamente observado no mesmo caminho de uma localização
  ativa. Preserva IDs existentes, mas não afirma igualdade de conteúdo, hash verificado ou
  atualização de `last_seen_at`.
- `new_file_candidate`: arquivo diretamente observado sem localização ativa naquele caminho.
  Não é um Asset definitivo, não recebe UUID e não constitui importação. Um caminho ocupado
  apenas por localização histórica `missing` também permanece candidato novo.
- `inconclusive`: informação insuficiente para classificar como arquivo conhecido ou candidato,
  como observação não-arquivo ou evidência não confirmada.
- `blocked`: contradição estrutural impede proposta confiável, como avaliação inválida, raiz
  divergente, escopo divergente, snapshot malformado, caminhos ativos conflitantes ou identidade
  física contraditória.

O status global `ready`, `inconclusive` ou `blocked` resume diagnósticos sem promover qualquer item
a operação executável.

## Raízes, caminhos e escopo

A compatibilidade exige o mesmo UUID de `LibraryRoot`, correspondência textual exata entre o
caminho configurado declarado no contexto, o caminho do snapshot e o caminho absoluto observado,
e o mesmo `ScanScope` nos três contratos. Uma identidade física de raiz disponível deve coincidir;
se estiver ausente, o plano é inconclusivo. Identidade divergente bloqueia.

Caminhos relativos usam a sintaxe POSIX lexical já adotada pelo catálogo e pelo scanner. A
comparação é textual exata. Caixa e Unicode são preservados: não há `casefold`, NFKC, remoção de
acentos ou reutilização da normalização de tags. Caminhos fora do escopo, absolutos, não canônicos
ou com `..` tornam o snapshot inválido. O planner não tenta descobrir a política real do volume.

Escopo recursivo cobre descendentes; escopo não recursivo cobre apenas filhos diretos. Uma
diferença de recursividade ou caminho inicial bloqueia a comparação, em vez de ampliar o alcance
implicitamente.

## Avaliações parciais e ausência

Observações diretas e estruturalmente válidas de execuções `partial` ou `cancelled` podem produzir
informação positiva dentro do escopo conhecido. O status global permanece inconclusivo e nenhuma
ausência é deduzida. `root_unavailable` e `failed` preservam diagnósticos sem converter uma lista
vazia em prova negativa. Uma avaliação estruturalmente inválida bloqueia todos os seus itens.

Mesmo uma avaliação `complete` não autoriza `missing`: a enumeração não é snapshot atômico e esta
etapa não possui política transacional de transição. Localizações conhecidas não observadas não
geram item nem alteração.

## Identidade física, conteúdo e ambiguidades

Identidade física é evidência local, pontual e potencialmente reutilizável. Se a evidência
registrada e a observada no mesmo caminho divergirem, o item é bloqueado. Se a evidência antes
registrada existir mas a observação atual não a fornecer, o item conhecido permanece positivo,
com resultado global inconclusivo. A mesma identidade física em localizações ativas de Assets
distintos torna o snapshot contraditório; no mesmo Asset ela apenas é compatível com hardlinks
potenciais e não provoca alteração.

SHA-256, tamanho, mtime, basename e timestamps não são usados para selecionar ou fundir Assets.
Hashes iguais em Assets distintos continuam distintos. O plano sempre registra que conteúdo não
foi verificado e jamais promove estado de hash.

## Integração futura

Um aplicador transacional futuro deverá revalidar a versão/estado lido, definir autorização,
registrar auditoria, aplicar operações atômicas e tratar concorrência. Ele não poderá interpretar
automaticamente este plano como comando, nem transformar a ausência de um item em `missing`.
Políticas de criação, reconciliação, movimento, merge e exclusão permanecem fora da 04B.2.
