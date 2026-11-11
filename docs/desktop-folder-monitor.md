# Acompanhamento de novas imagens

Status: implementado no desktop normal. Adicionar pastas registra a raiz para acompanhamento.
A biblioteca verifica essas raízes ao abrir. No Linux, notificações inotify disparam uma nova
verificação após agrupar eventos por 500 ms. Uma checagem a cada dez segundos recupera
mudanças sem notificação. Não pesquisa outros diretórios do computador.

O indicador mostra andamento, novas imagens e falhas. **Atualizar pastas agora** antecipa a
próxima checagem. A galeria é atualizada preservando a seleção e o visualizador aberto.

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

Testes usam árvores e imagens sintéticas: adição com sessão aberta, reinício, pasta vazia,
subpastas inicialmente vazias, idempotência, raiz substituída, raiz indisponível, pausa antes de
anotar e arquivo de âncoras inseguro. O smoke Electron adiciona um JPEG durante a execução sem
nova seleção nem atualização manual e verifica a miniatura decodificada na pasta aberta. Teste manual: adicionar uma imagem
à pasta registrada, aguardar a checagem e repetir com o aplicativo fechado.
