# Acompanhamento de novas imagens

Status: implementado no desktop normal. Adicionar pastas registra a raiz para acompanhamento.
A biblioteca verifica essas raízes ao abrir. No Linux, notificações inotify disparam uma nova
verificação após agrupar eventos por 500 ms. Uma checagem a cada dez segundos recupera
mudanças sem notificação. Não pesquisa outros diretórios do computador. Ao selecionar uma
subpasta de uma raiz disponível já cadastrada, o desktop orienta atualizar a pasta principal.
Os cartões mostram o nome da raiz e a subpasta de cada ocorrência. Basta adicionar a pasta pai:
seus descendentes existentes e novos são acompanhados recursivamente, inclusive após reabrir
o aplicativo. Em **Pastas → pasta pai**, a galeria inclui imagens de toda a árvore dessa raiz;
abrir uma subpasta restringe a galeria aos arquivos diretamente nela e permite navegar às filhas.

O indicador mostra andamento, novas imagens e falhas. **Atualizar pastas agora** antecipa a
próxima checagem e força uma nova consulta da tela, mesmo se a revisão do catálogo não mudou.
A atualização renova miniaturas e Propriedades, preservando a seleção de arquivos existentes
e o visualizador aberto. A seleção de um item que desapareceu só é limpa após confirmar que
todas as suas localizações estão ausentes em raízes disponíveis.

Excluir uma subpasta inteira é detectado mesmo sem novas imagens. Após uma observação completa,
as ocorrências removidas passam a `missing`. A galeria normal e o Calendário deixam de mostrar
Assets cujas ocorrências estão todas confirmadas ausentes em raízes disponíveis. Raízes offline,
ocorrências sobreviventes, candidatos a movimento e Assets sem localização não são prova de
exclusão e permanecem visíveis. O catálogo conserva UUIDs, metadata, anotações e álbuns; não há
exclusão lógica nem escrita nos originais como efeito da atualização.

## Contrato

O main fornece um arquivo privado de âncoras físicas, index-roots.json, no perfil library-state.
Cada âncora liga catálogo e raiz por identidade física. Não há migração SQLite. Raízes antigas
com arquivos conhecidos são validadas antes de registrar a âncora; raízes antigas vazias precisam
ser selecionadas uma vez. Uma pasta nova selecionada vazia funciona também após reiniciar.

O backend abre uma sessão independente por raiz e ciclo. Reutiliza concessões, preparação,
paginação e aplicação transacional existentes. Acompanhamento não esgota concessões da sessão
interativa. Ações de primeiro plano pausam e recolhem o trabalho; uma transação admitida termina
antes da ação. Resposta desconhecida bloqueia novas aplicações até reabrir a biblioteca.

Diretórios são conferidos sem seguir links. Notificações não fornecem caminhos para importação.
Assinaturas de diretórios e metadados de arquivos evitam reler imagens quando nada mudou. Até
32 raízes mantêm notificações e assinatura em memória. Ao reiniciar, uma leitura completa confere cada
raiz. Limites: 2.000 entradas, profundidade 32, até 21 passagens com lotes de 100. Pastas maiores
exigem divisão. Uma raiz indisponível não impede as demais. Nenhum original é escrito.

## Limitações e validação

O monitor cadastra adições em raízes verificadas e decodifica os candidatos nos workers existentes.
Um arquivo parcial que falha na validação fica fora do lote. Uma gravação posterior dispara nova
checagem, inclusive quando não houve mudança no nome. Mudanças durante a própria leitura podem
adiar a conclusão da varredura até a próxima tentativa.

Em raízes com âncora válida, alteração, exclusão ou substituição de um arquivo conhecido não
impede novas adições. A raiz substituída continua rejeitada. Com a raiz ancorada, o monitor reconcilia caminhos após uma observação completa e estável.
Dentro da mesma raiz, um destino livre e inequívoco com a mesma identidade física, tamanho e
mtime conserva o Asset e o ID da localização ativa. O caminho anterior fica no catálogo como
observação ausente do mesmo Asset. Se o caminho desapareceu e o destino já tem outro registro
ou a identidade é ambígua, o caminho antigo passa a ausente e os Assets continuam separados.
Uma raiz indisponível ou uma varredura incompleta não altera a disponibilidade dos arquivos.
O monitor não grava na mídia. O SQLite continua na mesma versão de esquema.

Na vista de uma pasta, o catálogo filtra pelo UUID da raiz antes de paginar e mostra adições
recentes primeiro.
Na página inicial da raiz, `gallery.list` recebe `root_id` sem `folder_path`: o filtro inclui
todos os descendentes antes da paginação. A primeira página devolve também `subfolders`,
considerando o caminho vazio quando `folder_path` não foi fornecido. Nas páginas de subpastas,
`folder_path` continua explícito, com o contrato anterior de filhos imediatos. Não há novo
parâmetro, migração ou raiz criada para cada subpasta.

O desktop real envia `exclude_missing=true` em `gallery.list`, inclusive retry/paginação,
e em `calendar.summary`. O filtro é aplicado antes da paginação, vincula o cursor ao escopo e
usa a mesma política nas contagens anuais, mensais, diárias, parciais e sem data. A API Python
mantém `exclude_missing=false` por padrão para leituras históricas. Ambos os métodos exigem
booleano estrito. Miniaturas antigas não permanecem visíveis após mudar a disponibilidade.

Testes usam árvores e imagens sintéticas: adição com sessão aberta, reinício, pasta vazia,
subpastas inicialmente vazias, idempotência, raiz substituída, raiz indisponível, pausa antes de
anotar e arquivo de âncoras inseguro. O smoke Electron adiciona um JPEG durante a execução sem
nova seleção nem atualização manual e verifica a miniatura decodificada na pasta aberta. Teste manual: adicionar uma imagem
à pasta registrada, aguardar a checagem e repetir com o aplicativo fechado.
