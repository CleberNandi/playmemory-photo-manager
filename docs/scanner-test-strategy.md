# Estratégia de testes para um futuro inventário

## Objetivo e limites

Planejar testes determinísticos para contratos de observação, sem implementar ou executar um
scanner nesta etapa. Todos os artefatos futuros devem ser sintéticos e criados em diretórios
temporários; fotografias pessoais, volumes reais e sidecars pessoais são proibidos.

## Oráculos comuns

Cada cenário deve verificar separadamente:

1. evidência coletada, incluindo origem, escopo e resultado;
2. classificação como observação, inferência ou falha;
3. alteração permitida no catálogo;
4. ausência de escrita na árvore inventariada;
5. atomicidade: falha parcial não produz `missing`, hash `verified` ou reconciliação indevida.

Arquivos sintéticos podem conter bytes fixos; não precisam ser imagens decodificáveis salvo quando
um futuro extrator exigir uma fixture mínima gerada no próprio teste.

## Cenários essenciais

| Cenário | Preparação sintética | Resultado esperado |
|---|---|---|
| Diretório vazio | Raiz temporária acessível e vazia | Inventário bem-sucedido, zero entradas; somente localizações conhecidas e cobertas pelo escopo podem futuramente tornar-se `missing` |
| Fotografia sintética | Fixture mínima ou bytes fixos com extensão conhecida | Uma ocorrência `present`; tipo de mídia não deve ser inferido além da evidência disponível |
| Mesmo arquivo, caminhos diferentes | Duas entradas que referenciam a mesma identidade física quando a plataforma permitir | Duas `FileLocation`; hardlink comprovado pode manter um Asset |
| Cópias exatas | Dois arquivos independentes com os mesmos bytes | SHA-256 igual, identidades físicas distintas e Assets distintos; nenhum merge automático |
| Hardlink | Criar link físico dentro da mesma raiz | Mesmo `filesystem_id` no alcance definido, duas localizações, sem confundir caminho com identidade |
| Symlink | Links interno, quebrado, cíclico e para fora da raiz | Não seguir por padrão; registrar ou rejeitar conforme contrato futuro, sem escape da raiz |
| Caminhos Unicode | Nomes com acentos, formas NFC/NFD e caracteres não ASCII | Preservação reversível; colisões avaliadas pela política real da raiz, não por normalização de tags |
| Renomeação | Inventariar, renomear e inventariar novamente | Só reconciliar automaticamente com file-id estável, caminho anterior ausente no mesmo ciclo e atributos compatíveis |
| Raiz offline | Tornar a raiz configurada inacessível como unidade | Raiz e localizações `offline`; nenhuma localização `missing` |
| Arquivo ausente | Remover entrada após um inventário anterior; executar inventário completo da raiz disponível | Candidato a `missing` sem apagar Asset, anotações ou histórico |
| Falha de permissão | Subárvore ou arquivo sem permissão em ambiente controlado | Resultado parcial/erro explícito; ausência nessa área não prova `missing` |
| Alteração durante leitura | Modificar ou substituir arquivo entre leitura inicial e final | Hash não promovido a `verified`; observação marcada instável e sem reconciliação automática |

## Variações de portabilidade

Executar, quando suportado pelo CI, uma matriz Linux/Windows com:

- separador nativo convertido para o formato persistido POSIX;
- raiz Unix, letra de unidade e caminho UNC sintético;
- volumes ou filesystems case-sensitive e case-insensitive, sem pressupor comportamento pelo nome
  do sistema operacional;
- nomes Unicode equivalentes e não equivalentes no volume real do teste;
- estabilidade e reutilização potencial do identificador físico;
- criação de hardlink e symlink condicionada à capacidade e permissão do ambiente, com skip
  explícito em vez de sucesso presumido.

## Falhas e concorrência

- Cancelamento antes e depois da enumeração parcial.
- Entrada removida entre enumeração e leitura de atributos.
- Entrada substituída no mesmo caminho por conteúdo diferente.
- Raiz desmontada ou desconectada durante o ciclo.
- Dois inventários concorrentes da mesma raiz.
- Escrita concorrente no catálogo durante a preparação de resultados.
- Erro ao persistir um lote, comprovando rollback sem perda da evidência anterior.
- Colisão de caminho sob a política de caixa/Unicode da raiz.

## Propriedades de segurança

Os testes futuros devem capturar snapshot de nomes, bytes, tamanhos e mtimes antes e depois para
demonstrar que o scanner é read-only. Também devem provar que não há criação de sidecar,
thumbnail, arquivo temporário ou lock dentro da raiz observada e que nenhuma operação física de
exclusão, movimento ou merge é emitida.

## Decisões pendentes para tornar os testes executáveis

- Formato público do resultado de observação e dos erros parciais.
- Definição do escopo e identificador de um ciclo bem-sucedido.
- Adaptador de filesystem injetável versus testes somente com filesystem temporário real.
- Política de caminho por raiz e representação de volume/file-id.
- Critério exato de estabilidade durante hashing.
- Caso de uso autorizado a persistir transições após validar evidências.

Os resultados D01–D05 poderão adicionar cenários de compatibilidade, mas não devem enfraquecer os
oráculos de segurança definidos pelos ADRs.
