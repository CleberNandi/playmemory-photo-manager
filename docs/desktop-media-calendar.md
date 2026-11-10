# Imagens reais e calendário de captura — incremento testável

## Comportamento

A biblioteca produz miniaturas reais de 256 × 160 e abre uma prévia orientada por EXIF
(até 1280 × 960) pelo botão Abrir imagem ou duplo clique. A prévia oferece ajuste à janela,
100%, ampliação/redução e fechamento por Escape. Não é um editor nem um visualizador de
resolução original. GIF animado e imagens de múltiplas páginas usam somente o primeiro quadro.
O nome do cartão prioriza o nome do arquivo; o caminho relativo completo fica no tooltip e
nas propriedades.

Calendário/Ano apresenta os anos de captura do catálogo inteiro. Escolher um ano apresenta os
meses; escolher um mês apresenta os dias, inclusive anos bissextos. Escolher um dia consulta
os itens daquele período, com paginação no backend e cursor vinculado ao filtro. Mês e Dia
na barra abrem diretamente esses níveis. Sem data consulta os itens sem captura selecionada.
As contagens não dependem das 24 imagens inicialmente carregadas nem dos filtros locais de
texto/favoritos/pasta. Datas parciais permanecem no nível de precisão conhecido; nunca recebem
um dia artificial. Abrir calendário recolhe as propriedades para dar espaço à navegação.

## Matriz deste incremento

| Formato | Catalogação | Miniatura e prévia | Observação |
| --- | --- | --- | --- |
| JPEG/JPG | Sim | Sim | Comum e progressivo; orientação EXIF na representação |
| PNG | Sim | Sim | Inclui transparência na entrada; representação RGB |
| WebP | Sim | Sim | Primeiro quadro |
| GIF | Sim | Sim | Primeiro quadro, sem reprodução da animação |
| BMP/DIB | Sim | Sim | Decodificador Pillow |
| TIFF | Sim | Sim | Primeira página |
| AVIF | Sim | Sim | Codec do pacote Pillow instalado |
| ICO | Sim | Sim | Imagem escolhida pelo decodificador de ícone |
| HEIC/HEIF e RAW | Pendente | Pendente | Exigem adapters/codecs e evidências próprias |
| SVG/PDF/EPS e outros | Não habilitado | Não habilitado | Sem execução de renderizadores externos |

Reconhecer cabeçalho não garante decodificação completa: um arquivo catalogado ainda pode ter
miniatura indisponível se estiver truncado, offline, alterado ou exceder o orçamento do decoder.
Não há promessa de suporte universal a qualquer variante de imagem.

## Contratos e preservação

- Pillow é a única dependência nova, motivada por formatos comuns, JPEG progressivo, orientação e
  leitura EXIF. O lockfile fixa a versão. Referência: [formatos Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html).
- `jpeg_structural_v1` permanece intacto como parser. A preparação aceita também o perfil
  `raster_header_v1`, com MIME derivado do formato detectado. O preflight da seleção repete
  a verificação e exige o mesmo resultado e fingerprint antes da transação.
- Somente o processo de aplicação extrai EXIF dos arquivos selecionados, por descritor já
  confinado e antes da transação. Observações e projeção são gravadas na mesma transação dos
  novos Assets; falha em metadata reverte o lote. Não se faz escrita como efeito de consulta.
- DateTimeOriginal válido precede DateTimeDigitized. O valor bruto e offsets observados ficam
  em metadata. Offset inválido não é adivinhado; valor local sem offset permanece flutuante.
  Data inválida é preservada com erro de parse. Metadata acima do orçamento não é truncada e
  publicada como observação completa. Não se usa data de importação como captura.
- Catálogos anteriores continuam abrindo e exibindo miniaturas quando a identidade física
  registrada confere. Datas de Assets antigos não são extraídas automaticamente: eles podem
  aparecer em Sem data. Para validar a extração nova, use outro catálogo de teste.
- UUID, ausência de hash, anotações, originais e sidecars permanecem preservados.

## Representações e lifecycle

`thumbnail.get` e `preview.get` aceitam apenas Asset ID dentro da sessão ativa. A ocorrência vem
do catálogo. O backend valida ancestralidade sem links, mount, inode, tamanho e mtime antes de
passar um descritor somente leitura ao decoder; revalida a ligação e o fingerprint ao terminar.
Mudança de identidade não vira localização missing nem reconciliação automática.

O decoder roda em processo Linux separado, com morte ao perder o pai, limite de endereço de
512 MiB, CPU de 4 s, deadline de 5 s e saída de no máximo 160 KiB. No máximo quatro jobs ficam
ativos. A ponte continua bombeando eventos e responde pending até a saída ser drenada e o filho
reaped; o frontend consulta com deadline e descarta respostas após desmontagem. Ambiente do filho
não inclui o token da ponte. Isso contém recursos e falhas; não é uma sandbox de segurança do SO.

O cache é somente memória, com até 32 representações e chave por Asset/variante/fingerprint,
sem paths públicos ou originais no DOM. Fechar/trocar biblioteca elimina o cache, encerra os
processos e exige reap; enquanto ainda há filhos, o comando retorna busy para uma nova tentativa.
Nenhum arquivo de thumbnail ou catálogo adicional é criado no acervo.

`calendar.summary` recebe somente um período validado e devolve pares compactos período/contagem;
`gallery.list` aceita capture_period com ano, mês, dia ou undated. Consultas permanecem somente
leitura e sem acesso à mídia. Sem timezone não há conversão para UTC ou timezone da máquina.

## Teste manual

Na raiz do checkout:

```sh
uv sync --locked
pnpm --dir desktop install --frozen-lockfile
PLAYMEMORIES_DESKTOP_LIBRARY_LAB=1 PLAYMEMORIES_DESKTOP_INGESTION_LAB=1 pnpm --dir desktop start
```

1. Crie um catálogo novo fora da pasta de imagens de estudo. Preserve seu catálogo anterior.
2. Adicione uma pasta com JPEG comum/progressivo e PNG; prepare, revise, selecione e catalogue.
3. Confira miniaturas, nomes e propriedades. Abra uma imagem, teste zoom e Escape.
4. Abra Calendário, percorra ano, mês e dia. Compare com a data EXIF de uma imagem conhecida.
5. Confira Sem data para imagens sem EXIF. A data de catalogação não deve preencher essa lacuna.
6. Reabra o catálogo e confira persistência dos itens e das datas.

Diálogos nativos e comportamento no KDE dependem da homologação manual do usuário. Os smokes
substituem somente as seleções/confirmações nativas por fixtures sintéticas.

## Evidências automatizadas

- `uv sync --locked`, 658 testes Python, Ruff, formatação e whitespace aprovados.
- 119 testes desktop em 19 arquivos; typecheck, ESLint e build aprovados.
- Fixtures geradas por Pillow validam cada formato da matriz, aplicação, miniatura e prévia.
- Testes cobrem proveniência EXIF/offset, data inválida, precisão parcial, 50 capturas além da
  primeira página, cursor incompatível, rollback de metadata, substituição de arquivo, symlink
  em ancestral, root offline e timeout com reap e liberação de descritores.
- Ponte autenticada real: PNG e JPEG progressivo atravessam preparação/aplicação em workers;
  calendário e representações são consultados sem receber paths do renderer.
- Electron headless real: seleção/revisão/catalogação, miniaturas decodificadas, prévia aberta,
  navegação ano/mês/29 de fevereiro/fotos do dia e originais intactos. Smoke demo também aprovado,
  incluindo paginação, propriedades, resize, retry e preload ausente.

Essas evidências usam somente mídia sintética. Não constituem homologação universal de variantes,
codecs, câmeras RAW ou diálogos KDE.

### Correção após teste manual — 2026-11-10

Os prints confirmaram miniaturas, prévia em parte das imagens e anos extraídos do acervo de
estudo. Também mostraram `NaN` no cabeçalho do calendário e uma prévia indisponível.

O cabeçalho agora usa condições booleanas explícitas: o short-circuit numérico não renderiza
`NaN` nem `0`. A prévia passou a adaptar qualidade JPEG e, quando necessário, dimensões para
caber nos mesmos 160 KiB. Não se aumentou o limite da ponte, não se alterou o original e não
é necessário recriar o catálogo para receber essa correção. Um teste com imagem sintética de
alta entropia demonstra que a codificação anterior ultrapassava o limite e que a nova prévia
é decodificável dentro do orçamento. Isso reproduz uma causa possível da falha observada;
o arquivo específico do print não foi usado nos testes.

O botão Abrir imagem também ganhou uma linha própria, separado da disponibilidade. Regressões:
659 testes Python, 120 testes desktop, typecheck/lint/build e smoke Electron de imagens/calendário.

### Barra de visualização fixa

A barra central de Miniaturas/Detalhes/Calendário/Propriedades permanece no topo do painel
durante a rolagem, com fundo opaco. Um smoke no Electron mede a posição da barra e dos cartões
antes/depois da rolagem: a barra permanece e os cartões se deslocam. A evolução posterior de
marcação, persistência e filtro global está em [Favoritos no desktop](desktop-favorites.md).
