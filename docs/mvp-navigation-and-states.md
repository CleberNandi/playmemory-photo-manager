# Navegação e estados do MVP

## Arquitetura de informação

Uma janela principal reúne navegação, galeria, visualizador e detalhes. Perspectivas não ganham
galerias próprias: compartilham seleção, filtros, ordenação e componentes.

```text
Biblioteca
├── Todas as fotos
├── Pastas
├── Datas
├── Álbuns
└── Tags
Ferramentas
└── Duplicatas exatas
Configurações
├── Biblioteca e raízes
├── Catálogo e backup
├── Thumbnails e cache
└── Acessibilidade e aparência
```

### Estrutura da janela

- **Barra lateral:** perspectivas e ferramentas; contagens somente quando baratas/confiáveis.
- **Cabeçalho contextual:** título, breadcrumb, busca, filtros, ordenação e alternância grade/lista.
- **Área principal:** galeria virtualizada ou estado contextual.
- **Barra de seleção:** aparece com uma ou mais seleções; apenas ações válidas no contexto.
- **Painel de detalhes:** lateral, redimensionável e reutilizado na galeria/visualizador.
- **Central de atividades:** jobs atuais e recentes; não bloqueia navegação quando seguro.

O visualizador abre sobre o contexto atual e preserva posição, filtros e seleção ao fechar.
Configurações abrigam preferências duradouras, não tarefas frequentes. Adicionar pasta e
catalogar ficam na Biblioteca; analisar duplicatas fica em Ferramentas.

## Conteúdo por área

### Biblioteca

“Todas as fotos” é a entrada padrão após abrir um catálogo. Pastas refletem FileLocations; Datas
refletem projeções com proveniência; Álbuns e Tags refletem organização virtual. Um Asset com
múltiplas localizações aparece uma vez nas perspectivas lógicas e pode expor todas as ocorrências
nos detalhes. Em Pastas, a ocorrência física selecionada precisa ficar clara.

### Galeria

Grade é padrão para exploração visual; lista acrescenta nome, tipo, data e disponibilidade. Cards
contêm thumbnail/fallback, seleção, tipo e no máximo indicadores essenciais. Metadata extensa,
hashes e caminhos completos pertencem ao painel de detalhes.

Ordenação deve ser explícita e estável: data escolhida + ID como desempate, nome + ID ou data de
catalogação + ID. Sem uma data válida, o item entra em “Data desconhecida”, não em posição
inventada.

### Visualizador e detalhes

O visualizador oferece imagem, anterior/próximo no resultado, zoom, ajustar e 100%. Não oferece
edição no MVP. O painel organiza:

1. título, descrição, rating e favorito;
2. álbuns e tags;
3. data escolhida e proveniência;
4. propriedades técnicas extraídas;
5. arquivo: raízes, caminhos relativos, disponibilidade e observações;
6. diagnóstico: Asset ID, estado de hash e detalhes avançados sob expansão.

### Busca e filtros

Busca é transversal ao contexto atual. Filtros mínimos: tipo, intervalo de data, pasta, álbum,
tag, rating/favorito e disponibilidade. A UI só oferece filtros cujo backend e dados existam.
Filtros ativos aparecem como chips removíveis, são serializáveis no histórico de navegação e não
alteram o conteúdo do catálogo.

### Revisão de duplicatas

A ferramenta usa três níveis na mesma área:

1. **Escopo e análise:** raízes/pastas, extensões e explicação de leitura SHA-256.
2. **Lista de grupos:** estado, quantidade, decisão, bloqueios e economia apenas estimada.
3. **Grupo/plano:** comparação de todos os membros, escolha/motivo, Assets/FileLocations e plano
   não executável.

“Candidato” significa candidato teórico do plano, não arquivo autorizado para remoção. Não usar
ícone de lixeira, botão de quarentena ou CTA “Limpar”. O CTA final é “Salvar/Gerar plano de
revisão”; depois, “Revalidar” ou “Analisar novamente”.

## Modelo comum de estados

Todo estado deve responder: o que aconteceu, o que continua seguro/disponível, qual é a ação
seguinte e se algo foi persistido. Mensagens técnicas detalhadas ficam expansíveis e copiáveis sem
expor dados privados por padrão.

| Estado | Apresentação e ações | Regra funcional |
| --- | --- | --- |
| Biblioteca não selecionada | Explicação curta; “Criar biblioteca” e “Abrir biblioteca” | Cancelar não cria ou migra catálogo |
| Biblioteca vazia | Convite para adicionar pasta; link para entender catálogo local | Só após catálogo válido aberto e zero Assets; diferente de zero resultados |
| Biblioteca offline | Conteúdo catalogado permanece; raízes afetadas identificadas; “Localizar raiz” e “Tentar novamente” | Não marcar localizações como `missing`; desabilitar decoder/hash |
| Arquivo indisponível | Placeholder no item; caminho/raiz e última observação; localizar/tentar novamente | Pode ser offline, ausente ou falha de acesso; não apagar Asset |
| Imagem não decodificável | Fallback de arquivo, erro sanitizado e detalhes ainda acessíveis | Não confundir com thumbnail ausente; não altera prova SHA-256 |
| Thumbnail ausente | Placeholder neutro e geração/repetição em background | Thumbnail é cache regenerável; não bloquear organização |
| Catalogação em andamento | Fase, escopo, processados, falhas, progresso determinado quando possível e Cancelar | Navegação permanece disponível; resultado parcial não prova ausência |
| Catalogação bloqueada | Lista agrupada de raiz/escopo divergente, evidência inválida, conflito ou permissão | Não oferecer “continuar mesmo assim”; voltar ao escopo ou analisar novamente |
| Erro recuperável | Impacto por item, “Tentar novamente”, “Ver detalhes” e preservação do trabalho válido | Falha isolada não vira falha total; retry deve ser idempotente |
| Erro fatal do catálogo | Impede escrita; oferece fechar, abrir outra biblioteca e instrução de backup/diagnóstico | Nunca recriar, sobrescrever ou migrar silenciosamente |
| Operação não autorizada | Explica que o plano não concede autorização e oferece voltar à revisão | Não expor bypass; registrar tentativa apenas se houver auditoria segura |
| Duplicatas encontradas | Resumo e lista de grupos; nenhum membro pré-marcado automaticamente | Igualdade binária não escolhe preservado nem funde Assets |
| Nenhuma duplicata encontrada | Escopo, extensões, horário e completude; “Alterar escopo” | Só declarar após análise completa; cancelada/parcial é inconclusiva |
| Grupo aguardando decisão | Todos os membros, seleção vazia e motivo requerido após escolha | Sem `keep`, não há candidatos no plano |
| Grupo bloqueado | Bloqueios junto aos membros e no resumo | Escolha humana não remove proteção, hardlink, dependência ou staleness |
| Arquivos modificados após análise | Banner “Plano desatualizado”, diferenças detectadas e “Analisar novamente” | Invalidar revisão; não atualizar snapshot/decisão silenciosamente |
| Plano pronto para revisão | Selo visual “Não executável”, grupos e ressalvas | Sempre `action_authorized=false`, `operations_performed=false` |

### Microcopy proibida no MVP

- “Excluir duplicatas”, “Mover para quarentena”, “Limpar agora”, “Restaurar” ou “Liberar espaço”
  como ação disponível.
- “Seguro para remover” ou “Cópia desnecessária”; o sistema só conhece igualdade de bytes e
  evidências contextuais.
- “Sem duplicatas” após cancelamento, falha, raiz offline ou cobertura parcial.
- “Foto original” como sinônimo automático do membro preservado.

## Comportamento responsivo

O alvo primário é desktop. Em largura reduzida, barra lateral recolhe, detalhes viram painel
sobreposto e a galeria reduz colunas; ações essenciais nunca dependem de hover. O visualizador
prioriza a imagem, mas mantém controles de teclado e um caminho claro para detalhes. Definir
breakpoints pela integridade do conteúdo, não por modelos de dispositivo.

## Virtualização e carregamento progressivo

- Consultas são paginadas e canceláveis, com ordenação determinística.
- A grade monta apenas viewport + margem e preserva foco/seleção fora do DOM.
- Primeiro vêm registros e placeholders; thumbnails visíveis têm prioridade; preview maior só é
  solicitado ao abrir o visualizador.
- Scroll rápido cancela/deprioriza trabalho obsoleto.
- Erro em um thumbnail não invalida o lote.
- Alteração de filtro substitui atomicamente o conjunto visível ou exibe skeleton identificado;
  não mistura resultados antigos e novos.
- A posição pode ser restaurada por Asset ID + ordenação, não por índice instável.

## Seleção e teclado

| Entrada | Resultado esperado |
| --- | --- |
| Setas | Move foco espacial/lista sem mudar seleção por acidente |
| Espaço | Alterna seleção do item focado |
| Enter | Abre visualizador ou grupo focado |
| Shift + clique/seta | Estende intervalo segundo ordenação visível |
| Ctrl/Cmd + clique | Alterna item mantendo os demais |
| Esc | Fecha painel/modal/visualizador em ordem e restaura foco |
| Ctrl/Cmd + A | Seleciona o escopo claramente rotulado; segunda etapa para todos os resultados quando aplicável |

Atalhos nunca acionam exclusão ou movimentação. A seleção é identificada por IDs estáveis; a UI
não materializa dezenas de milhares de objetos visuais para “todos os resultados”.

## Acessibilidade

- Alvo WCAG 2.2 AA, contraste e foco visível.
- Grade expõe papel, nome acessível, posição/conjunto quando confiável e estado selecionado.
- Thumbnails têm descrição funcional baseada em título/nome; metadata não é despejada como alt.
- Cores de disponibilidade, bloqueio e decisão sempre têm texto/ícone redundante.
- Zoom de interface a 200% preserva ações e leitura; painel não encobre foco.
- Progresso anuncia início, mudança relevante de fase, conclusão ou falha, não cada arquivo.
- Movimento reduzido e preferência de tamanho da grade são respeitados.

## Critérios de aceite por estado

1. Testes de componente cobrem todos os estados da tabela sem depender de filesystem real.
2. Testes de integração usam catálogo e árvores sintéticas para offline, permissão, decoder,
   cancelamento e mudança após análise.
3. Cada bloqueio tem mensagem, código tipado e próxima ação; string de exceção não é a única UI.
4. Focus trap existe somente em modal; ao fechar, o foco retorna ao originador.
5. Leitor de tela distingue item indisponível, selecionado, preservado e bloqueado.
6. Plano de duplicatas nunca renderiza comando de execução, mesmo quando todos os grupos estão
   `ready_for_review`.

## Dependências e decisões pendentes

- Definir APIs de consulta para árvore, timeline, galeria e busca antes de desenhar seus estados
  de carregamento finais.
- Escolher estratégia de lista/grade acessível compatível com virtualização e foco estável.
- Definir formato e privacidade dos jobs/relatórios persistidos.
- Validar terminologia (“biblioteca”, “catalogar”, “ocorrência”, “preservar”) em pesquisa.
- Medir breakpoints, tamanho de lote, cache e orçamento de memória; nenhum número observado existe
  ainda para a UI.
- Completar o Sony D01 e executar D02–D05 antes de usar comportamento legado como evidência de
  importação, datas, organização, metadata ou mudanças externas.
