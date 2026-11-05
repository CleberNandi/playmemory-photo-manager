# Desktop — área de trabalho em três painéis

Baseline: `6d6c842`. Incremento de apresentação; não altera IPC, Python, schema,
identidade, grants nem as políticas de acesso a arquivos.

## Comportamento implementado

- Navegação à esquerda, galeria central e propriedades integradas à direita, sem
  sobrepor a galeria. Divisores aceitam arrasto e controles range por teclado.
  Em janelas menores que 1000px, propriedades passam para baixo da galeria.
- Miniaturas com tamanho ajustável e tabela de detalhes usam a mesma seleção e
  paginação existente, com cursores opacos e proteção contra pedidos simultâneos.
- Pesquisa por título/caminho relativo, favoritos e agrupamento pelo nome público
  da raiz abrangem **somente os itens carregados**. Nomes de raiz iguais aparecem
  no mesmo grupo; isso não representa identidade de raiz nem um explorador físico.
- Arquivo reúne ações existentes de biblioteca. Exibir controla a apresentação;
  Ferramentas abre duplicatas exatas. Anotações continuam somente leitura.
  A barra de menus própria substitui o menu padrão Electron no Linux/Windows;
  o menu de aplicação macOS permanece nativo.
- Adicionar pastas abre o painel de preparação apenas com a capacidade fornecida
  pelo main. Recolher usa `hidden`, preserva o componente e o polling; não cancela
  a operação nem admite outra preparação. Fechar/trocar sessão desmonta o conjunto
  pela chave de sessão já existente e invalida respostas tardias.
- A seleção de mídia continua exclusiva dos diálogos nativos e do consentimento
  sobre o destino físico. Nenhum caminho novo é enviado pelo renderer.

## Limitações deliberadas

Calendário/Ano/Mês/Dia estão desabilitados: GalleryItem não expõe a projeção de
captura. `created_at` não será utilizado como data de captura (ADR-002).
Unidades, detecção de câmeras e árvore física de diretórios requerem contratos
próprios; não são simuladas nesta entrega. A preparação não aplica a proposta,
não cria Assets/FileLocations e não adiciona fotos à galeria.

As miniaturas disponíveis continuam sendo as ilustrações sintéticas do laboratório.
Não há fotos de demonstração externas, acesso direto a filesystem, novas
bibliotecas, migrações ou alterações de dependências.

## Validação

- Python: `uv sync --locked`, 554 testes, Ruff e formatação passaram.
- Desktop: typecheck, 101 testes (16 arquivos), ESLint e build passaram.
- Regressões novas: raízes/favoritos locais, alternância para tabela, seleção e
  pesquisa, retorno de foco após troca de modo, dimensionamento por range, indisponibilidade temporal e manutenção de
  polling ao recolher o fluxo, com interrupção após fechamento de sessão.
- A primeira suíte desktop falhou no teste antigo que exigia preparação sempre
  visível e teve timeout do backend durante instalação Python concorrente. O teste
  foi atualizado para a interação aprovada; após a instalação, a suíte completa
  passou sem ampliar timeouts nem mudar proteções.
- Inspeção gráfica em Chromium headless: seleção, abertura/recolhimento do fluxo,
  redimensionamento por teclado/arrasto e ausência de transbordamento da página
  em 1180, 1024, 1001, 800, 760 e 640px passaram com ponte sintética injetada.
  O primeiro download de Chromium falhou; a versão headless disponível foi obtida
  pelo espelho alternativo, sem alterar dependências do projeto.
- Validação gráfica nativa KDE e smokes Electron desta revisão ainda pendentes.
  O teste em navegador não comprova diálogos KDE, IPC/preload real nem cleanup
  de processos Electron.

## Roteiro nativo

1. Iniciar o laboratório com `PLAYMEMORIES_DESKTOP_LIBRARY_LAB=1
   PLAYMEMORIES_DESKTOP_INGESTION_LAB=1 pnpm --dir desktop start` (uma única linha).
2. Criar/abrir catálogo sintético em Arquivo e verificar três painéis.
3. Abrir Adicionar pastas, selecionar raiz sintética, preparar e recolher; reabrir
   e confirmar continuidade. Fechar/trocar biblioteca e rejeitar resultados antigos.
4. No demo, conferir seleção, propriedades, Escape, modos, filtros, paginação,
   redimensionamento por arrasto e teclado em 1180×760 e 800×600.
5. Confirmar ausência de aplicação, escrita em originais e calendário fictício.
