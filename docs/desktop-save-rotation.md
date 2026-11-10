# Salvar rotação no visualizador

Status: implementado conforme solicitação explícita do usuário: girar somente no visualizador,
com escolha entre substituir a própria imagem ou salvar uma cópia. Essa autorização vale para
a ação explícita de salvar; abrir, visualizar, girar a prévia e cancelar não alteram originais.

## Fluxo e limites desta versão

- O menu contextual da galeria não possui mais Girar. Os controles ficam na imagem aberta.
- Salvar alterações exige confirmação nativa, com destino físico e aviso de recompressão JPEG
  e possível normalização de metadados. Cancelar mantém a rotação pendente e não grava.
- Salvar como cópia abre o seletor nativo com nome sugerido e formato original. Nesta primeira
  versão, a cópia deve ficar na mesma pasta do original, com nome novo. Um arquivo existente
  nunca é substituído, mesmo que o diálogo do sistema permita confirmar sobrescrita.
- Fechar o visualizador ou navegar com rotação pendente oferece salvar, salvar cópia, descartar
  ou continuar editando. Durante a gravação, navegação e fechamento do visualizador ficam
  bloqueados. Encerrar o processo/app inteiro não oferece ainda um diálogo de edições pendentes.
- PNG e JPEG de imagem única, até 64 MiB e 40 milhões de pixels. Outros formatos e animações
  não são regravados. A interface desabilita gravação para tipos catalogados sem suporte.
- A gravação decodifica novamente o original em resolução integral, aplica orientação EXIF e
  a rotação escolhida, sem redimensionar. Nunca salva a prévia limitada a 1280 × 960.
- PNG preserva pixels/alpha após a transposição e os campos reconhecidos de texto, EXIF, ICC,
  DPI, gamma, sRGB, cromaticidade e transparência. Chunks privados desconhecidos não têm garantia
  de preservação. JPEG é reencodificado com qualidade 95/subsampling 0: não é rotação sem perdas.
  EXIF/ICC reconhecidos são preservados/normalizados; não há garantia de preservar todos os
  campos proprietários, miniaturas embutidas ou outros segmentos de metadados.

## Identidade e atualização

Substituir mantém UUID de Asset, localização, favoritos e anotações. Atualiza inode, tamanho e
mtime observados, remove hash antigo e seu estado verificado e acrescenta uma observação de
edição no namespace catalog. A captura selecionada anterior não é transformada em data de edição.
Por segurança, substituir é recusado se houver hardlinks ou múltiplas ocorrências no mesmo Asset;
nesses casos, salvar cópia continua disponível.

Uma cópia recebe outro UUID e localização na mesma raiz. Não herda favoritos/anotações nem faz
merge por hash. Datas EXIF suportadas são extraídas do resultado dentro da transação de registro.
A galeria, propriedades, prévia e miniaturas são atualizadas após sucesso. O visualizador continua
no arquivo original após salvar cópia, com a rotação pendente zerada. A atualização da galeria
reconsulta a primeira página; páginas adicionais anteriormente carregadas precisam ser carregadas
novamente. Destinos em outras pastas/raízes ficam para exportação posterior.

## Fronteira de gravação

O renderer envia somente UUID do Asset, ângulo 90/180/270 e modo. O main resolve origem no backend,
obtém seleção/confirmação nativa e vincula o trabalho à sessão. Paths e detalhes do filesystem
não voltam ao renderer. Concessões de importação não são usadas como autorização de edição.

O backend mantém descritores da origem e ancestrais sem symlinks, verifica montagem, inode,
tamanho e mtime, além da identidade do catálogo. Um único encoder descartável recebe descritores
herdados de leitura da origem e escrita de arquivo temporário exclusivo na mesma pasta. Limites
Linux: 1 GiB de address space, 12 segundos CPU, 64 MiB de saída; supervisor encerra após 18 segundos.
A UI/main acompanha estado sem bloquear o protocolo. Trocas de biblioteca e importações são
recusadas durante o trabalho; cancelamento do diálogo não inicia worker ou transação.

O temporário é privado (0600). Antes de publicar, o backend revalida origem/diretórios e inicia
transação curta de catálogo. Cópia usa criação exclusiva por link, recusando colisões. Substituição
cria hardlink de backup da origem e recibo JSON privado, sincroniza ambos e publica o resultado
por rename no mesmo diretório. A transação reconcilia o catálogo; no caso de erro conhecido antes
da tentativa de commit, restaura o original ou remove apenas a cópia criada, após verificar inode.
A verificação do catálogo dentro da transação admite o journal criado pela própria conexão;
não altera a política de admissão de catálogos com journals preexistentes.

Após confirmação do commit, temporário, backup e recibo são removidos e o diretório sincronizado.
A cópia fica com permissão 0600; substituição preserva os bits comuns de permissão do arquivo
anterior, preservando também proprietário/grupo. Substituição é recusada para arquivo de outro usuário,
ACL estendida ou bits especiais; não amplia permissões silenciosamente. Atributos estendidos
user.* não têm garantia de preservação. Origem e destino não podem ser escolhidos por comando de shell.
A verificação/rename pressupõe o mesmo limite do lifecycle: processos hostis do mesmo usuário
não estão isolados. Não há compare-and-swap atômico contra todo tipo de alteração concorrente.

## Interrupções e recuperação

SQLite e filesystem não formam uma transação ACID conjunta. Uma queda de energia/processo entre
a publicação e o commit pode deixar a imagem nova com observações antigas no catálogo. O acesso
às imagens continua verificando a identidade física e falha fechado quando ela diverge.
Não há recuperação automática dessa janela nesta versão.

Em substituição interrompida, o diretório pode conter:

- `.playmemories-before-<job-id>.bak`: bytes anteriores, sem reencodificação;
- `.playmemories-before-<job-id>.json`: recibo com nome da origem, Asset, ângulo e fingerprints;
- `.playmemories-edit-<job-id>.tmp`: temporário eventualmente abandonado por morte abrupta.

Um erro na confirmação de commit não prova rollback: mantém backup/recibo, marca resultado
como desconhecido e bloqueia novas edições até reabrir a biblioteca. Nunca repete a gravação.
Reabrir não restaura backup nem resolve automaticamente o estado desconhecido. É necessário
conferir arquivo, recibo e catálogo antes de restaurar: se o commit ocorreu, restaurar somente
o arquivo quebraria novamente as observações do catálogo. Esses artefatos não são um histórico
de desfazer nem um backup permanente do acervo.

## Validação

Somente mídia e catálogos sintéticos nos testes. Casos: PNG com pixels/alpha assimétricos e data
EXIF/texto; JPEG em resolução original; cópia preservando bytes; UUID estável ao substituir;
colisão e destino externo; hardlink; ângulo inválido; origem modificada enquanto o worker executa;
rollback físico após falha de catálogo; commit executado com confirmação perdida, preservando
backup e bloqueando repetição. Testes TS cobrem confirmação/cancelamento nativo injetados, sessão,
perda de resposta, escolha de salvar ao sair, manutenção da edição ao cancelar e atualização.

Smoke Electron usa backend real e escolhas nativas injetadas apenas em seu diretório sintético:
salva cópia pela UI, verifica origem preservada, substitui e confirma Asset/localização, depois
reabre a biblioteca. Diálogos nativos de salvar e confirmação precisam de homologação KDE.

```sh
git switch feat/desktop-save-rotation
uv sync --locked
pnpm --dir desktop start
```

Teste manual com cópias descartáveis: abrir imagem, girar, salvar cópia com nome novo na mesma
pasta e comparar dimensões; depois girar e salvar alterações com confirmação. Cancelar os dois
diálogos, tentar nome existente e fechar/trocar imagem com rotação pendente. Conferir que Girar
não aparece no botão direito da galeria e que favoritos permanecem ao substituir.

## PNGs enviados para análise de datas

As cópias recebidas de WP12-DM-blue.png e WP12-LM.png têm 2048 × 2048 e não contêm EXIF,
campos de texto/data ou chunk tIME. O print Sony apresenta 4000 × 4000. Logo, não são evidência
suficiente para atribuir a data mostrada pelo Sony a um metadado específico do arquivo original.
Os anexos foram apenas lidos; não foram regravados nem adicionados ao repositório. Calendário por
data do arquivo e ampliação das fontes temporais continuam pendentes, separados da edição.
