# Visualizador: navegação e rotação temporária

Status: implementado. Continuação do menu contextual homologado pelo usuário no KDE.

## Comportamento

O visualizador oferece Anterior/Próxima e setas esquerda/direita. A sequência inclui somente
fotos carregadas e visíveis ao abrir o visualizador, na ordem da galeria. Atualizações da galeria
continuam em segundo plano, e a sequência aberta permanece estável. O visualizador não busca o restante do catálogo
nem carrega páginas automaticamente. Vídeos não entram nessa sequência. Os extremos desabilitam
a navegação correspondente, sem circular para o início. Nome e posição deixam essa cobertura
explícita. Uma imagem sem prévia não impede avançar para a seguinte.

Girar à esquerda/direita aplica passos de 90 graus à prévia já decodificada. Restaurar rotação
volta a zero. Ajustar usa a prévia reduzida e considera a orientação no encaixe. O botão 100%
e os controles de zoom solicitam uma renderização JPEG sem redimensionar, com orientação EXIF
aplicada. O layout permite rolar a imagem, inclusive em 90/270 graus. Propriedades mostra a
largura e altura gravadas no arquivo, antes da orientação EXIF.

A renderização integral tem limite de 40 megapixels na decodificação e de 16 MiB na saída.
A imagem passa pelo worker confinado e chega em blocos pelo IPC existente. Se a versão integral
ficar indisponível, o visualizador informa a falha e mantém a prévia ajustada quando disponível.

Maximizar ocupa a área do aplicativo, e Restaurar janela volta ao tamanho anterior.
Os botões de gravação aparecem enquanto houver rotação pendente em um formato gravável.

A rotação fica somente no visualizador. A continuação
[desktop-save-rotation.md](desktop-save-rotation.md) oferece Salvar alterações e Salvar como cópia,
com gravação explícita em resolução original. Sem salvar, o original não muda. Fechar/navegar com
rotação pendente pede uma decisão; ela não é mais descartada silenciosamente. Renomear continua
pendente, por envolver consistência entre filesystem e catálogo.

O diálogo permanece montado durante a navegação. A seleção e as propriedades acompanham a imagem
atual; ao fechar, foco volta à última miniatura visualizada. Escape é consumido pelo visualizador
para não fechar as propriedades. Respostas de prévias anteriores são descartadas, sem mostrar a
imagem antiga na seleção nova. Os limites de decodificação, transporte e cache existentes são
preservados. Nenhuma nova API de filesystem, dependência ou migração é adicionada.

## Validação

Testes de renderer cobrem passos e restauração, geometria em 90 graus com ajuste/100%, navegação
por botões e setas, extremos, manutenção do diálogo, reset de rotação, resposta antiga, foco e
seleção ao fechar. A ausência de Girar no menu da galeria é preservada pela lista de ações testada. O smoke Electron de laboratório
usa duas imagens sintéticas reais, verifica a caixa girada dentro do visualizador, navega com
botões/setas e confere a recuperação de foco. Demo e biblioteca gerenciada preservam os smokes.
O usuário homologou as ações anteriores do menu; os diálogos de gravação precisam de teste manual no KDE, assim como uso prolongado e janelas pequenas.

```sh
git switch feat/desktop-viewer-navigation
pnpm --dir desktop start
```

1. Abrir uma imagem e conferir nome/posição.
2. Girar à direita/esquerda, ajustar e testar 100% com rolagem.
3. Avançar com Próxima e escolher salvar ou descartar; voltar com seta esquerda.
4. Fechar com Escape e conferir seleção/propriedades da última imagem visualizada.
5. Conferir que o botão direito da galeria não possui Girar.
6. Reabrir o arquivo salvo e conferir a orientação; ajustes descartados não devem permanecer.
