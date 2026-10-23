# Matriz de requisitos para o Discovery Sony D01–D05

## Uso da matriz

Este documento é uma estrutura de recepção. Nenhuma linha abaixo afirma comportamento Sony: os
resultados D01–D05 ainda não estão disponíveis. Cada observação futura deve citar evidência
reproduzível e distinguir comportamento observado de interpretação.

### Critério de evidência

Para cada resultado, registrar versão do produto e sistema, preparação do cenário, ação executada,
resultado visível ou artefato inspecionado e limitações da observação. Ausência de evidência deve
permanecer “não observado”, nunca ser convertida em “não suportado”.

## Registro dos estudos

| Estudo | Escopo executado | Ambiente/versão | Evidência primária | Estado |
|---|---|---|---|---|
| D01 | A preencher | A preencher | A preencher | Pendente |
| D02 | A preencher | A preencher | A preencher | Pendente |
| D03 | A preencher | A preencher | A preencher | Pendente |
| D04 | A preencher | A preencher | A preencher | Pendente |
| D05 | A preencher | A preencher | A preencher | Pendente |

## Matriz de rastreabilidade

Adicionar uma linha por comportamento efetivamente observado. Não preencher “comportamento” ou
“evidência” por expectativa.

| ID | Requisito ou comportamento observado | Evidência | ADR relacionado | Capacidade já implementada | Lacuna | Prioridade proposta | Decisão pendente |
|---|---|---|---|---|---|---|---|
| SONY-D01-___ | Não observado | Não disponível | A avaliar | A avaliar | A avaliar | A avaliar | A avaliar |
| SONY-D02-___ | Não observado | Não disponível | A avaliar | A avaliar | A avaliar | A avaliar | A avaliar |
| SONY-D03-___ | Não observado | Não disponível | A avaliar | A avaliar | A avaliar | A avaliar | A avaliar |
| SONY-D04-___ | Não observado | Não disponível | A avaliar | A avaliar | A avaliar | A avaliar | A avaliar |
| SONY-D05-___ | Não observado | Não disponível | A avaliar | A avaliar | A avaliar | A avaliar | A avaliar |

## Vocabulário de classificação

- **Confirmado:** sustentado por evidência reproduzível do Discovery.
- **Hipótese:** explicação plausível ainda não demonstrada.
- **Não observado:** cenário não executado ou sem evidência conclusiva.
- **Incompatível:** conflito demonstrado entre comportamento observado e decisão vigente.
- **Fora do produto:** comportamento Sony que não é requisito deste projeto.

Prioridade proposta deve considerar segurança e domínio do PlayMemories Photo Manager, não apenas
paridade. Sugestão: `P0` para risco de perda/corrupção, `P1` para bloqueio do inventário seguro,
`P2` para compatibilidade relevante e `P3` para conveniência.

## Pontos de correlação após o Discovery

Quando houver evidência, avaliar sem presumir equivalência:

- identidade usada pelo Sony para caminho, arquivo, volume, cópia, hardlink e renomeio;
- comportamento diante de mídia removível offline e arquivo ausente;
- seguimento ou não de symlinks e atalhos;
- normalização de caixa, Unicode e caminhos no Windows;
- cálculo, persistência ou uso de hashes;
- efeitos físicos de organização, exclusão e edição de metadata;
- distinção entre metadata observada e escolhas do usuário;
- tratamento de falhas parciais, permissão e arquivo alterado durante leitura.

## Decisões protegidas

Resultados Sony não substituem automaticamente ADR-001, ADR-002 ou ADR-003. Qualquer divergência
deve produzir uma decisão explícita: manter a política própria, revisar um ADR com justificativa ou
classificar a paridade como fora do escopo. Não importar formatos proprietários ou semânticas não
demonstradas apenas para imitar o produto de referência.
