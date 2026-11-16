# Visualizador: navegação e rotação temporária

Status: implementado. Continuação do menu contextual homologado pelo usuário no KDE.

## Comportamento

O visualizador oferece Anterior/Próxima e setas esquerda/direita. A sequência inclui somente
fotos carregadas, visíveis e disponíveis ao abrir o visualizador, na ordem da galeria. Cartões
registrados como indisponíveis, offline ou sem localização têm abertura desabilitada e não
entram na sequência/carrossel. Registros com todas as ocorrências confirmadas ausentes ficam
fora da galeria normal, conservando seu histórico no catálogo; offline não é ausência. O mesmo
filtro se aplica às páginas carregadas pela navegação. Um arquivo que deixa de estar acessível
depois de abrir a sequência ainda pode produzir a mensagem de prévia indisponível, com retry.
Atualizações da galeria continuam em segundo plano e preservam as entradas da sequência aberta.
Ao usar Próxima no fim dos itens carregados, o visualizador pode buscar páginas adicionais com
o mesmo filtro, ignorando fotos indisponíveis. Vídeos não entram nessa sequência. Os extremos desabilitam
a navegação correspondente, sem circular para o início. Nome e posição deixam essa cobertura
explícita. Uma imagem sem prévia não impede avançar para a seguinte.

Um clique na foto abre o carrossel, que começa oculto. Outro clique na foto fecha o carrossel.
Escolher uma miniatura muda a foto e mantém o carrossel aberto.

O menu de contexto abre com o botão direito sobre a foto ou com Shift+F10 quando ela tem foco.
Girar à esquerda/direita aplica passos de 90 graus à prévia já decodificada. Restaurar rotação
volta a zero. Encaixar à janela usa a prévia reduzida e considera a orientação no encaixe. Tamanho
real (100%) e os controles de zoom solicitam uma renderização JPEG sem redimensionar, com orientação EXIF
aplicada. O layout permite rolar a imagem, inclusive em 90/270 graus. Propriedades mostra a
largura e altura gravadas no arquivo, antes da orientação EXIF.

A renderização integral tem limite de 40 megapixels na decodificação e de 16 MiB na saída.
A imagem passa pelo worker confinado e chega em blocos pelo IPC existente. Se a versão integral
ficar indisponível, o visualizador informa a falha e mantém a prévia ajustada quando disponível.

O visualizador ocupa a janela do aplicativo. As ações de gravação aparecem no menu de contexto
enquanto houver rotação pendente em um formato gravável.

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
2. Clicar na foto para abrir e fechar o carrossel. Pelo botão direito, girar, encaixar e testar 100% com rolagem.
3. Avançar com Próxima e escolher salvar ou descartar; voltar com seta esquerda.
4. Fechar com Escape e conferir seleção/propriedades da última imagem visualizada.
5. Conferir que o botão direito da galeria não possui Girar.
6. Reabrir o arquivo salvo e conferir a orientação; ajustes descartados não devem permanecer.
