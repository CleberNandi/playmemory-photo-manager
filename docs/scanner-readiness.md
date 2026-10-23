# Prontidão para inventário de mídia

## Escopo

Este documento prepara a discussão da Foundation 04. Ele não define um scanner, não altera os
ADRs existentes e não incorpora resultados do Discovery Sony D01–D05, ainda indisponíveis.

## Fatos confirmados

### Identidades e caminhos

- `Asset.id` é o identificador lógico imutável. Não deriva de caminho, conteúdo ou identidade do
  filesystem.
- `FileLocation` representa uma ocorrência vinculada a um Asset e a uma `LibraryRoot`, por caminho
  relativo. Caminhos absolutos são derivados, não são identidade de Asset.
- SHA-256 é evidência de conteúdo e não é único. Cópias byte a byte continuam sendo Assets
  distintos por padrão.
- `filesystem_id` é evidência opcional de identidade física dentro do alcance de uma raiz; o
  catálogo não define seu formato nem o trata como identidade global.
- Hardlinks devem ser múltiplas localizações do mesmo Asset quando a identidade física estável for
  demonstrada na mesma raiz.
- Symlinks não são seguidos por padrão. O modelo distingue `file` de `symlink` e exige alvo para o
  segundo, mas ainda não valida ciclos, links quebrados ou escapes.
- `(library_root_id, normalized_relative_path)` é único para localizações não `missing`. Uma
  localização histórica `missing` não reserva o caminho para sempre.
- Renomeio ou movimento não pode ser inferido apenas por nome, mtime, metadata ou similaridade.
  A continuidade automática exige as evidências combinadas do ADR-001.

### Contratos já implementados

- A aplicação aceita caminhos relativos em sintaxe POSIX canônica, rejeita caminhos absolutos e
  componentes `..`, e não consulta o filesystem.
- A criação pública de localização aceita somente `present` em raiz `available` ou `offline` em
  raiz `offline`. `missing` e `moved_candidate` não possuem transição pública.
- Um SHA-256 fornecido em `create_asset` pode ser apenas `unverified`. Não existe promoção pública
  para `verified`.
- Foreign keys, UUIDs canônicos, enums, integridade de associações e imutabilidade de `Asset.id`
  são protegidos pelo SQLite.
- A fachada usa transações `BEGIN IMMEDIATE`; schema e migrações não acessam arquivos.
- Nenhuma operação atual move, copia, altera ou exclui fotografia ou sidecar.

## Contrato conceitual de observação

Os termos abaixo evitam apresentar afirmações de origens diferentes como fatos equivalentes:

| Categoria | Significado | Exemplos | Pode fundamentar persistência factual? |
|---|---|---|---|
| Observação | Resultado obtido diretamente por uma operação read-only concluída | entrada enumerada, atributos lidos, bytes integralmente hasheados | Sim, com origem, instante e resultado preservados |
| Inferência | Conclusão derivada de duas ou mais observações | possível renomeio, possível duplicata | Somente como candidato, nunca como reconciliação automática |
| Declaração | Informação fornecida por usuário ou chamador sem verificação nesta camada | raiz configurada, nome exibido, caminho informado | Sim, se identificada como declaração; não como observação comprovada |

Uma observação bem-sucedida de uma raiz requer, no mínimo: a raiz correta e acessível; enumeração
concluída no escopo definido; nenhuma falha que torne a ausência ambígua; e identificação do ciclo
e do instante de observação. Sucesso de uma entrada não implica sucesso da raiz inteira.

### Condições por estado

- `present`: a entrada foi enumerada no caminho esperado durante uma observação bem-sucedida da
  parte relevante da raiz. Atributos ausentes permanecem desconhecidos.
- `missing`: a localização era conhecida, a raiz estava disponível, o caminho estava dentro do
  escopo, e uma enumeração completa e sem falhas relevantes não encontrou a entrada. Erro de
  permissão, cancelamento ou falha parcial não prova ausência.
- `offline`: a raiz ou volume não pôde ser acessado como unidade. Isso preserva a última
  localização conhecida e não implica `missing`.
- `moved_candidate`: observações sugerem continuidade, mas não satisfazem ou não podem provar as
  condições conservadoras de reconciliação. Não altera automaticamente o Asset.
- Hash `verified`: leitura integral bem-sucedida de um descritor estável, com SHA-256 concluído e
  verificação de que a entrada não mudou durante a leitura. Leitura parcial ou arquivo mutável
  mantém o hash ausente ou não verificado.

## Portabilidade

### Fatos

- O contrato persistido de caminho relativo usa `/`, independentemente do separador nativo.
- `LibraryRoot.normalized_path` é texto globalmente único, mas sua normalização é responsabilidade
  da aplicação futura.
- A normalização Unicode NFKC existente aplica-se a tags, não a caminhos.
- SQLite compara os caminhos com semântica binária padrão; isso não reproduz automaticamente a
  sensibilidade a caixa ou a normalização Unicode do volume.

### Lacunas reais

- Política canônica de raiz para Linux e Windows, incluindo letras de unidade, UNC, separadores,
  prefixos estendidos e barras finais.
- Representação e estabilidade do identificador de volume.
- Política por raiz para case sensitivity e equivalência Unicode; ela não pode ser inferida apenas
  do sistema operacional.
- Conversão reversível entre nome nativo e caminho relativo persistido.
- Tratamento de nomes reservados, componentes vazios, pontos finais e espaços significativos no
  Windows.
- Formato, alcance e possibilidade de reutilização de `filesystem_id` por plataforma.
- Detecção de colisões quando dois nomes nativos se tornam equivalentes sob a política escolhida.

## Limites operacionais recomendados

- O inventário futuro deve ser read-only e nunca escrever em originais ou sidecars.
- Não seguir symlinks por padrão; nunca atravessar a fronteira da raiz implicitamente.
- Não reconciliar, fundir Assets, verificar hash ou marcar `missing` a partir de evidência parcial.
- Não usar igualdade de hash como identidade lógica.
- Não excluir arquivos nem Assets como efeito de ausência.
- Separar coleta de evidências da decisão transacional que altera o catálogo.
- Tratar cancelamento, permissão negada, mudança durante leitura e indisponibilidade como resultados
  explícitos, não como listas vazias.

## Decisões pendentes

1. Unidade atômica de inventário: raiz inteira, subárvore ou lote identificável.
2. Representação de ciclo, escopo, resultado parcial e proveniência das observações.
3. Política de normalização de caminhos por raiz e detecção de colisões.
4. Contrato portátil para volume e `filesystem_id`.
5. Estratégia para detectar alteração entre `stat`, leitura e `stat` final.
6. Política de histórico de caminhos e transição conservadora para `missing`.
7. Fronteira entre scanner, avaliador de evidências e casos de uso do catálogo.

Nenhuma dessas decisões deve ser fechada com base em comportamento Sony ainda não observado.
