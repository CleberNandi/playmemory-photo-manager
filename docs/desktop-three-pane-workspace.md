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

## Correção de menus após teste nativo do usuário

- Menus de aplicação fecham ao escolher uma ação, clicar fora, sair com Tab ou
  perder foco da janela; só um menu fica aberto. Escape fecha e restaura o foco
  no título, sem fechar as propriedades simultaneamente.
- Setas cima/baixo navegam pelas ações habilitadas; esquerda/direita alternam os
  menus. As expansões de metadata permanecem independentes.
- Retirados triângulos de expansão e estilo de botão primário dos itens. Popups
  usam linhas planas, separadores e destaque de hover/foco. No demo, Arquivo
  informa sua indisponibilidade em uma opção desabilitada.
- Revalidação: 554 testes Python, Ruff, formatação, typecheck, 104 testes desktop
  (17 arquivos), ESLint e build. Chromium headless verificou exclusividade,
  clique externo, ação, Escape/foco e layout nos tamanhos anteriores.

## Álbuns virtuais no catálogo real

Abra **Álbuns** na barra lateral, dê um nome e clique em **Criar álbum**. Com um item
selecionado na galeria, escolha o álbum e use **Adicionar item selecionado**. **Abrir
álbum** mostra a coleção na mesma galeria, com paginação, filtros e visualizador.
Dentro da coleção, **Remover item deste álbum** desfaz apenas a associação. O item
continua na biblioteca.

A criação e a associação usam os comandos de catálogo existentes. Adicionar o
mesmo item novamente é idempotente. As associações persistem ao reabrir o catálogo
e respeitam a sessão ativa. O demo mantém a opção desabilitada.

Para excluir uma coleção, selecione-a e use **Excluir álbum**. A confirmação mostra seu
nome. O catálogo remove a coleção e seus vínculos. Os itens, originais e vínculos com
outros álbuns são preservados. Se a coleção estiver aberta, a galeria volta à Biblioteca.

## Câmeras e mídias conectadas no Linux

Em **Câmeras e mídias**, use **Detectar dispositivos** e **Atualizar dispositivos** depois
de conectar ou remover um aparelho. O backend consulta o sysfs local e lista interfaces
USB que anunciam a classe Still Imaging, cartões SD e armazenamento removível ou USB.
O painel identifica a classe anunciada pelo dispositivo. A detecção de protocolos USB
proprietários e a navegação/importação por PTP/MTP ficam pendentes. Para mídias montadas,
use **Adicionar pastas** para escolher uma pasta por meio do diálogo nativo.
