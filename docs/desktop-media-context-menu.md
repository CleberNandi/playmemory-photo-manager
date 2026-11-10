# Menu contextual e origem das imagens

Status: implementado, sem alteração de originais, dependências ou schema. Baseado no fluxo de
biblioteca principal persistente. Não introduz Rust nem migração do shell.

## Comportamento

Botão direito em uma miniatura ou linha da exibição Detalhes seleciona o Asset e abre um menu
nativo Electron: Visualizar, Abrir pasta que contém o arquivo, Localização do arquivo,
Adicionar/remover favorito e Propriedades. Shift+F10 ou a tecla de menu também o abrem a partir
do item focado. Cancelar mantém a seleção e devolve foco ao item. O popup usa o fechamento e
navegação de teclado do sistema; não cria um dropdown persistente na página.

Visualizar e Propriedades reutilizam os fluxos existentes. Favoritar usa o comando explícito
existente, sem repetição automática. Para disponibilidade catalogada diferente de available,
as opções físicas ficam desabilitadas; propriedades e favorito continuam disponíveis. Uma
observação catalogada como disponível não dispensa a verificação física na hora de localizar.

As propriedades começam com Origem do arquivo: nome, raiz e caminho relativo de cada ocorrência
conhecida. Botões permitem revelar a ocorrência no gerenciador de arquivos ou consultar o caminho
completo em um diálogo nativo. Com múltiplas ocorrências, a revelação escolhe deterministicamente
a primeira ocorrência disponível por ID de localização, não necessariamente a primeira listada
nas propriedades. Selecionar individualmente uma ocorrência fica para outro incremento.

Renomear e girar não foram adicionados: renomear requer operação consistente filesystem/catálogo;
a rotação futura deverá explicitar se é ajuste de visualização ou regravação autorizada.

## Fronteiras

O renderer envia apenas session_id e UUID do Asset através do preload restrito. Não escolhe path,
URL, comando de shell ou programa externo. O main consulta asset.details para montar as opções,
valida a sessão após o popup e executa asset.reveal para resolver o destino. Essa resposta com
path absoluto é exclusiva do transporte Python/main; ela nunca é retornada ao renderer.

asset.reveal exige sessão ativa e parâmetro único asset_id. O backend seleciona uma ocorrência
registrada como arquivo presente em raiz disponível, rejeita paths não canônicos, traversal e
profundidade excessiva, abre ancestrais com O_NOFOLLOW, confere montagem, arquivo regular,
dev/inode, tamanho e mtime observados, além de conferir os diretórios antes de devolver o destino.
Não lê pixels, não modifica arquivos e não reconcilia mudanças automaticamente.

O main usa shell.showItemInFolder, sem linha de comando e sem abrir o arquivo com seu aplicativo
associado. O diálogo com caminho completo é produzido pelo main, e uma confirmação de Abrir
pasta faz nova resolução física. Falhas públicas usam mensagens fixas sem paths ou exceções brutas.

A verificação vale para o instante da resolução: o gerenciador externo recebe um caminho, não
um descritor confinado. Uma mudança concorrente posterior ainda pode alterar o que ele mostra.
Essa ação somente revela arquivos; não autoriza escrita, execução ou exclusão. A API Electron
não confirma que o gerenciador abriu: requested significa solicitação emitida, não sucesso visual.
No Linux o gerenciador padrão é usado; no KDE espera-se o Dolphin. A seleção visual do arquivo
depende da integração disponível na sessão desktop.

## Validação

Testes Python usam somente catálogo e imagens sintéticos: resolução válida e bytes preservados,
sessão errada, campos extras, UUID inválido, arquivo ausente, symlink final, ancestral substituído,
conteúdo alterado, raiz offline e traversal injetado no catálogo.
Testes TypeScript cobrem a lista de ações, opções desabilitadas, cancelamento, caminho derivado
exclusivamente do backend, sessão alterada durante diálogo/popup, revalidação, rejeição de paths,
Shift+F10, favorito e descarte de resposta após desmontagem.
O smoke Electron com backend real verifica a resolução e a seção Origem do arquivo. Popup nativo,
fechamento ao clicar fora e abertura real do Dolphin precisam de homologação manual KDE.

```sh
git switch feat/desktop-media-context-menu
uv sync --locked
pnpm --dir desktop start
```

1. Adicionar uma pasta sintética; clicar com o botão direito numa miniatura.
2. Conferir fechamento com Escape e clique fora, depois testar Visualizar e Propriedades.
3. Testar Favoritar e o estado persistido, inclusive na exibição Detalhes.
4. Testar Abrir pasta: o gerenciador deve mostrar a pasta e, quando possível, selecionar o arquivo.
5. Consultar Localização completa nas propriedades e comparar com a pasta escolhida.
6. Focar o nome e usar Shift+F10; fechar o visualizador e conferir seleção/propriedades preservadas.
7. Com uma fixture removida/alterada externamente, conferir erro seguro sem abrir outro destino.
