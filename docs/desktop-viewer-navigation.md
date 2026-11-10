# Visualizador: navegação e rotação temporária

Status: implementado. Continuação do menu contextual homologado pelo usuário no KDE.

## Comportamento

O visualizador oferece Anterior/Próxima e setas esquerda/direita. A sequência inclui somente
fotos carregadas e visíveis no filtro atual, na ordem da galeria; não busca o restante do catálogo
nem carrega páginas automaticamente. Vídeos não entram nessa sequência. Os extremos desabilitam
a navegação correspondente, sem circular para o início. Nome e posição deixam essa cobertura
explícita. Uma imagem sem prévia não impede avançar para a seguinte.

Girar à esquerda/direita aplica passos de 90 graus à prévia já decodificada. Restaurar rotação
volta a zero; Ajustar calcula a caixa delimitadora considerando a orientação. Zoom 100% refere-se
à prévia derivada, não à resolução integral do original. O layout reserva a área correta para
rolagem quando o zoom excede a janela, inclusive em 90/270 graus.

O menu contextual ganhou Girar para a esquerda/direita, abrindo o visualizador já girado. As
opções físicas continuam desabilitadas para imagens catalogadas como indisponíveis e vídeos.
Esta etapa **não salva orientação no catálogo**, não modifica EXIF, não regrava imagem e não
gira miniaturas. Ao navegar ou fechar, o ajuste é descartado. A interface informa Rotação
temporária. Uma futura orientação persistida exigirá contrato próprio; renomear também continua
pendente, por envolver consistência entre filesystem e catálogo.

O diálogo permanece montado durante a navegação. A seleção e as propriedades acompanham a imagem
atual; ao fechar, foco volta à última miniatura visualizada. Escape é consumido pelo visualizador
para não fechar as propriedades. Respostas de prévias anteriores são descartadas, sem mostrar a
imagem antiga na seleção nova. Os limites de decodificação, transporte e cache existentes são
preservados. Nenhuma nova API de filesystem, dependência ou migração é adicionada.

## Validação

Testes de renderer cobrem passos e restauração, geometria em 90 graus com ajuste/100%, navegação
por botões e setas, extremos, manutenção do diálogo, reset de rotação, resposta antiga, foco e
seleção ao fechar. O menu é testado com ação de rotação simulada. O smoke Electron de laboratório
usa duas imagens sintéticas reais, verifica a caixa girada dentro do visualizador, navega com
botões/setas e confere a recuperação de foco. Demo e biblioteca gerenciada preservam os smokes.
O usuário homologou as ações anteriores do menu; as novas entradas de rotação precisam de teste
manual no KDE, assim como uso prolongado e janelas pequenas.

```sh
git switch feat/desktop-viewer-navigation
pnpm --dir desktop start
```

1. Abrir uma imagem e conferir nome/posição.
2. Girar à direita/esquerda, ajustar e testar 100% com rolagem.
3. Avançar com Próxima e voltar com seta esquerda: a nova visualização deve iniciar sem rotação.
4. Fechar com Escape e conferir seleção/propriedades da última imagem visualizada.
5. Usar botão direito → Girar para a direita e conferir 90 graus iniciais.
6. Reabrir normalmente: a rotação temporária não deve permanecer.
