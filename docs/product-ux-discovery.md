# Product UX Discovery 01

## Propósito e limites

Esta descoberta define o contrato de experiência do primeiro MVP do PlayMemories Photo Manager.
Ela não define aparência final, não homologa Electron ou Tauri e não autoriza movimentação,
quarentena, exclusão ou restauração. O produto continua local-first: os originais são a fonte de
verdade; catálogo, álbuns, tags e planos são dados derivados ou organizacionais.

Data da verificação: 2026-10-26. Branch documental: `docs/product-ux-discovery-01`.

## Evidências utilizadas

### Estado verificado

| Fonte | Estado observado | Uso nesta descoberta |
| --- | --- | --- |
| Photo Manager | `main` limpa em `32eb7b1ba3e5e259bd425c1523f125076bfb5d67`, sem remotos; 193 testes aprovados | Fonte de verdade das capacidades atuais |
| ADR-001 a ADR-004 | Aceitas no commit-base | Identidade, tempo, anotações, arquitetura e limites do shell |
| Sony Lab | `main` limpa em `78b754b60ecbaeeddae57b2e6a2568269c52cd6a` | Evidência dinâmica limitada e pendências D01–D05 |
| Duplicate Lab local | Branch `investigation/orb-mutual-false-positives`, limpa, em `96b214475dc56fa4e828f9c0bf9eb3b3b6db3a3f` | Estado local apenas; não foi alterado |
| Handoff Duplicate Lab | Commit `4a93464cb884cce7fbc1b69af5cbd9b0edbe424b`, lido por cópia temporária da branch `feat/exact-duplicate-review-plan` | Contrato read-only de grupos SHA-256, decisão, plano e revalidação |

Foram examinados o README, modelo de domínio, documentos das Foundations 02–04C.1, documentos de
convergência, ADRs, implementação e testes; no Sony Lab, os roteiros D01–D05, relatório funcional,
PoC de automação e evidências descritas da Fase 02C; no handoff, `photo-manager-handoff.md`,
`exact-duplicate-review-plan.md`, implementação e testes do plano exato. Nenhum laboratório foi
modificado e nenhuma fotografia pessoal foi usada.

### Observação, documentação e hipótese

| Classe | Evidência disponível | Consequência para o produto |
| --- | --- | --- |
| Implementado no Photo Manager | SQLite `STRICT`; Assets, FileLocations e LibraryRoots; álbuns, tags e anotações; scanner read-only; avaliação; plano de mudanças; autorização e aplicação de novos arquivos | Pode sustentar casos de uso, mas ainda precisa de adaptadores de consulta e UI |
| Observado dinamicamente no Sony | Alternância validada visualmente entre Miniaturas, Detalhes e Calendário; tabela com nome/tipo/datas; agrupamento temporal | Referência de capacidade, não um layout a copiar |
| Documentado pela Sony | Pastas gerenciadas, pesquisa, propriedades, labels, rating, importação e mídia mista | Inspira requisitos; não prova implementação ou modelo interno |
| Demonstrado no Duplicate Lab | Tamanho + SHA-256, grupos exatos, todos os membros, escolha/motivo, proteção, bloqueios, revalidação e plano sem operações | Referência funcional a integrar por contrato próprio |
| Não observado | Jornada Sony completa, estados vazios/offline/erro, D02–D05, busca/labels/álbuns em execução, comportamento de mudanças externas | Não deve ser descrito como comportamento Sony confirmado |

## Capacidades atuais e lacunas

| Área | Situação | Contrato real e lacuna para UX |
| --- | --- | --- |
| Abrir produto | Inexistente | Não há shell, frontend, processo de startup nem seletor de catálogo |
| Catálogo SQLite | Implementada | Migração e integridade existem; falta lifecycle de biblioteca, backup e apresentação de falhas |
| Raízes e localizações | Implementada em parte | Registro, leitura paginada e disponibilidade existem; escolha por diálogo e atualização de disponibilidade não são fluxo completo |
| Catalogação | Implementada em backend | `prepare → authorize → apply` cria Asset/FileLocation para seleção explícita; não extrai metadata, hash ou thumbnail |
| Pastas | Parcial | Localizações podem ser listadas por raiz; falta árvore/agregação e consultas próprias para grandes volumes |
| Datas | Parcial | Schema suporta projeção temporal e proveniência; ingestão atual não extrai/preenche data, e não há consulta de timeline |
| Visualização | Inexistente | Não há decoder, imagem em tamanho útil, zoom, orientação ou fallback |
| Metadados | Parcial | Schema representa metadata e anotações, mas não há extrator nem caso de uso público completo de leitura/escrita de metadata extraída |
| Álbuns e tags | Implementada em backend | CRUD essencial e associações existem; falta edição em lote, contagens, ordenação e UI |
| Busca e filtros | Inexistente | Não há FTS nem API combinatória de busca/filtro |
| Thumbnails | Somente persistência | Há tabela/referência; geração, cache, invalidação e serviço de entrega inexistem |
| Duplicatas exatas | Inexistente no produto | Handoff externo comprovou conceito, mas código/schema/contrato ainda não foram incorporados |
| Operações destrutivas | Deliberadamente inexistentes | Não apresentar controles de executar, quarentenar, excluir ou restaurar |

“Implementada” não significa pronta para interface. A UI depende de casos de uso públicos,
paginação estável, cancelamento, progresso e erros tipados; não deve consultar SQLite nem varrer o
filesystem diretamente.

## Princípios de experiência

1. **Biblioteca antes de ferramenta.** O ponto de entrada é a coleção do usuário, não um painel
   técnico de scanner.
2. **Uma coleção, múltiplas perspectivas.** Pastas, Datas, Álbuns e Tags mudam o recorte da mesma
   galeria; não duplicam telas ou Assets.
3. **Seleção persistente no contexto.** Trocar grade por lista, abrir detalhes ou percorrer itens
   não perde a seleção sem aviso.
4. **Proveniência visível.** Data, caminho, hash e metadata dizem sua fonte e seu estado de
   verificação; ausência de evidência não vira certeza.
5. **Longas tarefas são observáveis e canceláveis quando seguro.** O usuário vê fase, progresso
   determinado ou indeterminado, itens processados, falhas e resultado recuperável.
6. **Original protegido por padrão.** Organização virtual não move arquivos. Duplicidade é uma
   conclusão sobre bytes, não permissão para agir.
7. **Divulgação progressiva.** Informações essenciais ficam junto da foto; detalhes técnicos e
   diagnósticos aparecem sob demanda.

## Contrato funcional do MVP

### Biblioteca e catalogação

O MVP deve permitir criar/abrir um catálogo local, adicionar uma pasta como `LibraryRoot`, fazer
uma leitura recursiva read-only, apresentar candidatos e aceitar uma seleção explícita antes de
catalogar. Resultados parciais nunca são apresentados como varredura completa. Uma nova execução
deve distinguir itens já catalogados de candidatos e não deve inferir `missing`.

A biblioteca permanece utilizável quando uma raiz está offline: Assets e organização continuam
visíveis; ações que requerem bytes são desabilitadas com motivo e ação de “Localizar raiz” ou
“Tentar novamente”.

### Exploração e organização

A mesma galeria deve aceitar os contextos Pasta, Data, Álbum, Tag e resultado de busca. A visão
por Data só inclui itens com projeção temporal apropriada e oferece um recorte “Data desconhecida”.
Enquanto extração temporal não existir, a interface não pode fabricar datas a partir do nome ou
apresentar mtime como captura sem rótulo explícito.

Álbuns são virtuais e tags são anotações do catálogo. Adicionar/remover associação não toca no
arquivo. Seleção múltipla deve suportar associação em lote de modo transacional ou relatar
claramente resultados por item; o backend atual precisa ser ampliado para esse contrato em lote.

### Duplicatas exatas

O MVP de duplicatas é somente leitura e revisão:

1. escolher escopo entre raízes/pastas catalogadas e iniciar análise;
2. inventariar ocorrências elegíveis e calcular SHA-256 com detecção de alteração;
3. exibir somente grupos com dois ou mais membros byte a byte iguais;
4. relacionar cada membro a todos os `Asset` e `FileLocation` correspondentes, sem fundi-los;
5. permitir escolher exatamente uma ocorrência para preservar e exigir um motivo não vazio;
6. mostrar protegidos, hardlinks, sidecars/dependências, raiz offline e divergências como bloqueios;
7. gerar e revalidar um plano de revisão com `action_authorized=false` e
   `operations_performed=false`;
8. nunca oferecer execução, quarentena, exclusão ou restauração.

O plano deve ser tratado como retrato versionado e local. Seu checksum detecta alteração
acidental, não autentica comandos. Mudança em tamanho, identidade, timestamps observáveis,
link count ou SHA-256 torna o grupo desatualizado e exige nova análise/revisão.

## Dependências técnicas antes de uma UI funcional

| Dependência | Necessária para | Prioridade |
| --- | --- | --- |
| Lifecycle seguro de catálogo e preferências de biblioteca | Abrir/selecionar biblioteca | MVP |
| Queries paginadas e ordenadas por contexto; contagens | Galeria, pastas, álbuns, tags | MVP |
| Serviço de thumbnail com cache regenerável e placeholders | Galeria utilizável | MVP |
| Decoder/loader read-only com orientação e erros tipados | Visualizador | MVP |
| Extração read-only mínima de metadata e data com proveniência | Datas e detalhes | MVP |
| API de busca/filtros e índices medidos | Encontrabilidade | MVP |
| Jobs locais com progresso, cancelamento e retomada definida | Scan, ingestão, thumbnails e hashes | MVP |
| Contrato interno de duplicatas ligado a Asset/FileLocation | Revisão exata | MVP |
| Operações em lote transacionais para organização | Seleção múltipla | MVP |
| PoC e decisão final do shell | Empacotamento desktop | Antes da implementação de UI, conforme ADR-004 |

## Critérios de usabilidade e desempenho

Não existem benchmarks do produto para galeria, thumbnails, busca ou startup. Os valores desta
seção são metas iniciais a validar com corpus sintético; não são resultados observados nem
critérios já homologados.

### Critérios funcionais mínimos

- paginação com ordenação determinística, sem duplicação ou lacuna entre páginas;
- virtualização cujo número de elementos visuais dependa do viewport, não do total de Assets;
- placeholder imediato e prioridade para thumbnails visíveis, com falha isolada por item;
- seleção preservada fora do DOM e “selecionar tudo no resultado” com escopo explícito;
- setas, Enter, Espaço e Esc com foco visível e ordem previsível;
- progresso com fase, escopo, concluídos e falhas; cancelamento termina em estado inequívoco;
- alvo WCAG 2.2 AA, zoom a 200% e estado nunca comunicado somente por cor.

### Metas iniciais de responsividade

| Tema | Meta proposta |
| --- | --- |
| Primeira apresentação | Shell utilizável em até 2 s e primeiro lote da galeria em até 1 s após biblioteca aberta, em máquina de referência a documentar |
| Virtualização | DOM/render tree limitado ao viewport mais margem; no máximo 3 vezes os cards visíveis |
| Rolagem | Meta de 60 fps; percentil 95 dos frames abaixo de 16,7 ms durante rolagem contínua no cenário medido |
| Paginação | Lotes iniciais de 100–300 itens, sujeitos a medição |
| Interação | Resposta visual a seleção, filtro e abertura em até 100 ms; operação maior mostra feedback em até 500 ms |
| Memória | Crescimento associado ao viewport/cache, não linear ao total; teto numérico definido após PoC |

### Testes de carga

O cenário de referência proposto contém 50.000 Assets e ao menos 100.000 FileLocations gerados
sinteticamente, sem fotografias pessoais. Deve medir abertura, consulta paginada, mudança de
perspectiva, filtros, seleção de até 10.000 resultados, rolagem, cache frio/quente e consumo de
memória. Registrar hardware, SO, tamanho/formato do banco, distribuição de pastas, estado do
cache e percentis; não aceitar apenas média. Esse corpus é meta de teste, não evidência de
desempenho homologado.

### Testes de estresse

Executar separadamente, fora do gate funcional mínimo, aumento progressivo além do cenário de
carga até identificar degradação, indisponibilidade de memória, filas excessivas ou limites do
SQLite/cache. Incluir cancelamento repetido, scroll rápido, troca contínua de filtros e falhas de
thumbnail/decoder. O objetivo é descobrir limites e garantir falha controlada, não prometer uma
capacidade numérica antes da medição. Benchmarks do Duplicate Lab não são métricas da futura UI.

## Marcos de produto

### MVP Preview

Primeira experiência demonstrável, ainda sem reduzir o compromisso do MVP funcional:

- aplicação aberta por um shell ainda sujeito à homologação prevista no ADR-004;
- biblioteca sintética consultável por uma fronteira real do backend, sem acesso direto da UI ao
  SQLite ou ao filesystem;
- galeria virtualizada com carregamento progressivo;
- visualizador read-only;
- painel de detalhes com dados disponíveis e ausências explícitas;
- estados básicos de carregamento, vazio, arquivo indisponível, falha de thumbnail/decoder e erro
  recuperável.

O Preview valida a fatia vertical e a linguagem da experiência. Não declara catalogação,
organização, busca ou duplicatas concluídas e não substitui os critérios do MVP funcional.

### MVP funcional

Primeira entrega completa definida nesta descoberta:

- catalogação controlada;
- navegação por pastas e datas;
- álbuns, tags, busca, filtros e seleção múltipla;
- análise de duplicatas binárias exatas;
- revisão de grupos com todos os Assets e FileLocations relevantes;
- escolha explícita da ocorrência a preservar e motivo;
- plano dry-run não executável e sem autorização de ação.

## Priorização recomendada

### Obrigatório para o MVP

- criar/abrir biblioteca e adicionar raiz local;
- catalogação controlada e reexecutável, com progresso, cancelamento seguro e relatório;
- galeria virtualizada por Pasta e Data, incluindo data desconhecida;
- visualizador read-only, painel de detalhes e estados de indisponibilidade;
- seleção múltipla, álbuns e tags;
- busca textual e filtros mínimos por tipo, data, pasta, álbum, tag, rating/favorito e
  disponibilidade, conforme dados realmente existentes;
- análise de duplicatas exatas, comparação de membros, escolha/motivo e plano não executável;
- navegação por teclado, WCAG 2.2 AA e recuperação de erros.

### Desejável após o MVP

- favoritos/rating em lote, smart albums, filtros salvos e edição temporal manual;
- importação por cópia verificada a partir de dispositivo;
- histórico/auditoria mais amplo, gestão de cache e diagnósticos avançados;
- suporte inicial a vídeo no mesmo modelo, após codecs e metadados medidos;
- relações explícitas entre RAW/JPEG/original/editada.

### Futuro

- similaridade perceptual, rostos, mapa e recursos online;
- escrita interoperável em XMP/sidecar;
- colaboração ou catálogo em rede;
- quarentena, exclusão, restauração e consolidação de duplicatas, somente após protocolo seguro,
  journal durável, autorização vinculada ao plano e testes de falha.

## Critérios de aceite desta descoberta

- Cada jornada identifica pré-condição, caminho feliz, exceções e resultado persistido.
- Cada controle proposto pode ser associado a capacidade implementada ou dependência declarada.
- Estados offline, incompleto, indisponível e desatualizado nunca simulam sucesso.
- A revisão de duplicatas mostra Assets e FileLocations sem transformar SHA-256 em identidade.
- Nenhum texto ou controle promete operação destrutiva.
- Metas propostas aparecem separadas de evidências e métricas observadas.
- A arquitetura de informação reutiliza galeria, visualizador e painel de detalhes entre contextos.

## Questões abertas e riscos

1. Qual é o lifecycle de criação, escolha, bloqueio e backup do arquivo de catálogo?
2. Quais formatos de imagem e perfis de cor compõem o MVP, e qual decoder será isolado?
3. Qual precedência temporal mínima será implementada primeiro e como expor tempo sem timezone?
4. Como modelar jobs e progresso sem acoplar o frontend ao scanner síncrono atual?
5. A escolha de preservação vive em nova entidade do catálogo ou em artefato versionado externo?
6. Como mapear uma ocorrência do scan de duplicatas a uma FileLocation sem confiar em caminho
   absoluto ou snapshot desatualizado?
7. Quais filtros precisam de novos índices e quais metas são realistas após o primeiro benchmark?
8. Electron só poderá ser confirmado após a PoC requerida pelo ADR-004.
9. O Sony Lab ainda não observou D01 completo nem D02–D05; não há base para copiar seus fluxos,
   estados de erro, regras de importação, metadata ou reconciliação.
