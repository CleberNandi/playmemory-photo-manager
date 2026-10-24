# Catalogação controlada — Foundation 04C.1

## Escopo

A Foundation 04C.1 implementa o primeiro fluxo vertical que pode persistir observações:

`Scanner → Evidence Evaluator → Change Planner → autorização explícita → aplicador → Catalog`

O caso de uso recebe uma `LibraryRoot` já cadastrada e uma raiz de filesystem escolhida
explicitamente. Ele observa a raiz sem escrever nela, avalia a evidência, monta um snapshot lógico
do catálogo, produz um plano e só cadastra candidatos selecionados pelo chamador.

Não há reconciliação, `missing`, merge, deduplicação, leitura EXIF, hash verificado, thumbnail,
sidecar, CLI ou integração Sony. Todo arquivo regular autorizado cria um Asset independente. O
tipo do Asset e o media type são declarações explícitas da seleção; não são inferidos do nome,
conteúdo ou file-id.

## API pública

```python
from playmemories_photo_manager.catalog import AssetKind, Catalog
from playmemories_photo_manager.catalog_ingestion import (
    CandidateSelection,
    apply_ingestion,
    authorize_ingestion,
    candidate_reference,
    prepare_ingestion,
)

proposal = prepare_ingestion(catalog, root.id, root.normalized_path)
selections = tuple(
    CandidateSelection(
        candidate_reference(proposal.plan, change.relative_path),
        AssetKind.PHOTO,
        "image/jpeg",
    )
    for change in proposal.plan.changes
    if change.classification == "new_file_candidate"
)
authorization = authorize_ingestion(proposal.plan, selections)
report = apply_ingestion(catalog, proposal, authorization)
```

`IngestionProposal` preserva o `ScanResult`, o `EvidenceAssessment`, o `CatalogSnapshot`, o
`PlanningContext` e o `CatalogChangePlan`. Antes de escrever, o aplicador recalcula avaliação e
plano e exige igualdade estrutural. `IngestionReport` preserva `run_id`, raiz, fingerprint do plano
e um resultado tipado por item. Assim, o chamador distingue criação, localização preexistente,
candidato ignorado, bloqueio, conflito concorrente e falha transacional.

## Autorização

A autorização é uma decisão de um chamador confiável, não autenticação nem prova criptográfica.
Ela contém:

- fingerprint determinístico do plano concreto;
- `run_id` e `library_root_id`;
- referências não posicionais `(run_id, library_root_id, relative_path)`;
- classificação de Asset e media type declarados para cada candidato selecionado.
- fingerprint da decisão cobrindo exatamente o conjunto e as declarações selecionadas.

`None` significa ausência de autorização. Uma autorização válida com seleção vazia significa a
decisão explícita de não cadastrar candidato algum. Candidatos inexistentes, repetidos ou de outro
plano são rejeitados. Alterar ou ampliar uma autorização já emitida invalida o fingerprint da
decisão. Esse mecanismo detecta alteração acidental ou estrutural, mas continua não sendo uma
assinatura criptográfica contra um chamador hostil. `CatalogChangePlan.authorizes_catalog_mutation`
não participa da autorização.

Planos bloqueados, avaliações estruturalmente inválidas e mudanças inconclusivas são rejeitados.
O schema atual não persiste identidade física da raiz. Por isso o plano preparado normalmente é
`inconclusive` somente por `root_identity_unavailable`; a 04C.1 admite especificamente esse único
limite quando a raiz foi escolhida explicitamente, o caminho absoluto coincide textualmente e
todas as mudanças são determinadas. Qualquer outro warning de inconclusão impede aplicação.
Assessments com cobertura incompleta, raiz indisponível ou confinamento não demonstrado também são
rejeitados independentemente do status resumido pelo planner; isso exclui a caminhada path-based
atual do Windows e resultados sem proveniência de ambiente.

## Transação e conflitos

O lote selecionado é uma única transação `BEGIN IMMEDIATE`. Dentro dela, o catálogo:

1. revalida existência, caminho e disponibilidade da LibraryRoot;
2. consulta novamente cada caminho ativo autorizado;
3. compara tipo declarado, tamanho, mtime e identidade física observada;
4. executa preflight do lote inteiro;
5. cria UUIDs aleatórios, Asset e FileLocation no mesmo commit.

Um conflito em qualquer caminho impede todas as criações do lote. Falha após inserir um Asset e
antes da FileLocation causa rollback, portanto não deixa Asset órfão. Foreign keys e o índice
único parcial do SQLite continuam sendo a última linha de defesa contra referências inválidas e
caminhos ativos duplicados.

Falha de commit inicia rollback. Se o próprio rollback falhar, o resultado é
`transaction_failed`, informa que o estado transacional é incerto e o dono da conexão deve
descartá-la ou fechá-la; nenhuma confirmação de persistência é emitida.

O `read_version` é um digest determinístico do snapshot lógico usado pelo plano, não uma versão
transacional do SQLite. Ele serve para rastreabilidade. A segurança de aplicação vem da
revalidação sob `BEGIN IMMEDIATE` da raiz e dos caminhos selecionados; mudanças fora desses
caminhos não ampliam nem invalidam silenciosamente a autorização.

## Idempotência

Reaplicar o mesmo plano não cria outro Asset quando já existe uma localização ativa com os mesmos
atributos persistidos e a mesma declaração de tipo/media type: o resultado é `already_exists`.
Uma nova execução do fluxo classifica esse caminho como `known_location_observed` e também não o
recria. Se o caminho passou a pertencer a estado incompatível, o lote retorna conflito.

Essa idempotência é somente por cadastro de caminho e evidências registradas. Ela não prova que os
bytes permaneceram estáveis. Dois caminhos, inclusive cópias byte a byte ou hardlinks, recebem
Assets distintos nesta fundação; file-id nunca funde identidade lógica.

Uma substituição física detectável no mesmo caminho ativo não cria, religa ou funde Asset nesta
fase. Antes de reportar uma localização conhecida, o aplicador compara file-id namespaced, tamanho
e mtime da observação com o snapshot. Divergência rejeita o proposal; igualdade continua sem provar
estabilidade dos bytes, pois file-id pode ser reutilizado e tamanho/mtime podem coincidir.
Um `filesystem_id` legado sem o prefixo produzido por este fluxo também bloqueia essa confirmação,
em vez de ser interpretado com semântica inventada.

## Proveniência e TOCTOU

O report liga o resultado ao `run_id` e mantém o `ScanResult` completo no proposal. O schema atual,
porém, não possui coluna para `scan_run_id` nem timestamp por entrada. `started_at` e `finished_at`
são limites da execução, não o instante exato em que cada arquivo foi observado. Para não fabricar
um `last_seen_at`, a localização criada pela 04C.1 deixa esse campo `NULL`.

O aplicador não relê o filesystem: ele não pode afirmar que o arquivo ainda existe ou mantém os
mesmos bytes no commit. Tamanho, mtime e identidade física persistidos são evidências da varredura,
não garantias atuais. A janela entre observação e commit permanece uma limitação explícita. Uma
fundação futura poderá acrescentar proveniência persistente ou revalidação por descritor somente
por decisão de schema revisada.

## Limitações e decisões adiadas

- Persistência durável do `run_id` e do intervalo temporal da observação.
- Revalidação do arquivo imediatamente antes do commit sem quebrar a separação de camadas.
- Política portátil para identidade de raiz e filesystem.
- Unidade transacional para lotes maiores que o primeiro fluxo local.
- Movimento, ausência, hashes, metadata, versões, merge e deduplicação.

Nenhuma dessas lacunas autoriza inferir `missing`, verificar hash ou fundir Assets.
