# Avaliação de evidências do filesystem — Foundation 04B.1

## Escopo

A Foundation 04B.1 avalia, de forma pura e determinística, um `ScanResult` já produzido pelo
scanner. Ela não consulta o filesystem, não abre SQLite e não cria, altera ou reconcilia Assets,
raízes ou localizações. Sua saída descreve o que a coleta sustenta, o que permanece inconclusivo e
quais condições impedem decisões futuras.

```python
from playmemories_photo_manager.evidence import evaluate
from playmemories_photo_manager.scanner import scan

scan_result = scan("/tmp/synthetic-media")
assessment = evaluate(scan_result)
print(assessment.coverage, assessment.structural_validation)
```

O exemplo pressupõe uma árvore sintética já existente. O avaliador não usa o caminho e não produz
efeitos externos.

## Contratos públicos

`EvidenceAssessment` preserva `run_id` e `ScanStatus` da execução original e contém:

- `coverage`: cobertura classificada no escopo declarado;
- `structural_validation`: `valid` ou `invalid`;
- `accepted_entries`: observações diretas aceitas de um resultado coerente;
- `inconclusive_entries`: inferências não confirmadas ou todas as entradas quando a estrutura é
  inválida;
- `failures`: as falhas originais, sem conversão para observações negativas;
- `inferences`: candidatos estruturados, atualmente apenas hardlinks potenciais;
- `reasons`: códigos diagnósticos com severidade e caminho relativo opcional;
- `portability_limitations`: limites de plataforma que permanecem aplicáveis;
- `decision_impediments`: condições que bloqueiam tipos de decisão posteriores.

Todos os contratos são dataclasses congeladas. A avaliação não corrige silenciosamente o
`ScanResult` nem atribui probabilidades ou pontuações de confiança.

## Cobertura e validação

Uma execução `complete` é classificada separadamente como escopo recursivo completo ou escopo não
recursivo completo. O segundo caso não cobre descendentes. `partial`, `cancelled`,
`root_unavailable` e `failed` permanecem classificações distintas. Um resultado contraditório
recebe cobertura `invalid`, nenhuma entrada aceita e razões de erro.

A validação verifica UUID v4 canônico, timestamps UTC ordenados, raiz exigida pelo status,
caminhos relativos canônicos e confinados ao escopo declarado, duplicidades, tipos de contrato em
runtime, timestamps brutos, tamanhos coerentes com o tipo, identidade física utilizável e sem
contradições, relação entre diretórios observados e enumerados e coerência entre status e falhas.
Uma falha parcial nunca vira arquivo ausente; raiz indisponível nunca prova ausência.

## Proveniência e limites de certeza

Uma entrada `direct_observation` continua sendo evidência pontual do filesystem. Tamanho e
timestamps descrevem o instante da consulta; timestamp de filesystem não é data de captura.
`PhysicalIdentity` é evidência local e reutilizável, não identidade lógica. Duas entradas regulares
com a mesma identidade física produzem somente uma inferência `potential_hardlink`; isso não cria
ou une Assets. Mesmo tamanho não produz inferência de conteúdo e nenhum hash é declarado
verificado.

Enumeração completa significa que o escopo foi percorrido segundo o contrato do scanner. Não é
snapshot atômico, não garante estabilidade posterior e, isoladamente, não autoriza uma conclusão
de `missing`.

## Plataforma e confinamento

O scanner registra `ScanEnvironment` com a família de plataforma e o mecanismo usado:

- POSIX com `descriptor_relative`: a caminhada usa descritores e `O_NOFOLLOW`, mas a enumeração
  ainda não é atômica;
- `path_based`, incluindo Windows atual: não há garantia equivalente contra substituição
  concorrente por um agente local;
- proveniência ausente: o avaliador registra explicitamente que plataforma e confinamento não
  foram demonstrados.

O avaliador não deduz plataforma pelo formato do caminho e não consulta o host. Semântica de
caixa/Unicode e estabilidade de IDs físicos continuam definidas pelo filesystem.

## Razões e impedimentos

Razões de erro identificam contradições estruturais específicas. Razões informativas preservam
limites como enumeração não atômica, conteúdo não verificado, identidade física não lógica,
escopo não recursivo e confinamento baseado em caminhos.

Impedimentos não são decisões. Eles informam à próxima camada que estrutura inválida, cobertura
incompleta, raiz indisponível, conteúdo não verificado, identidade lógica não confirmada ou
confinamento não demonstrado impedem conclusões específicas. A lista deliberadamente não contém
uma decisão `missing`.

## Fronteira com a Foundation 04B.2

Uma etapa futura poderá comparar avaliações com estado previamente conhecido e preparar planos de
mudança. Ela deverá definir autorização, escopo de ausência, histórico e transações próprias. A
04B.1 não consulta o catálogo, não decide persistência, não cria Assets, não registra
FileLocations, não promove hashes e não reconcilia movimentos.
