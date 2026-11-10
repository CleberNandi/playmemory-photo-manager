# Acompanhamento de novas imagens

Status: implementado no desktop normal. Adicionar pastas registra a raiz para acompanhamento.
A biblioteca verifica essas raízes ao abrir e, enquanto o aplicativo está aberto, a cada dez
segundos mais o tempo de leitura. Não pesquisa outros diretórios do computador.

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

Diretórios são conferidos sem seguir links. Assinaturas de diretórios evitam reler imagens quando
não houve adições; o cache guarda até 32 raízes. Ao reiniciar, uma leitura completa confere cada
raiz. Limites: 2.000 entradas, profundidade 32, até 21 passagens com lotes de 100. Pastas maiores
exigem divisão. Uma raiz indisponível não impede as demais. Nenhum original é escrito.

## Limitações e validação

Este incremento detecta adições. Não reconcilia remoções, renomeações ou conteúdo alterado de
arquivos conhecidos; essas mudanças podem bloquear a raiz até revisão. Substituição da raiz ou
mudança de identidade física falha fechada. Não há notificação instantânea do sistema operacional.

Testes usam árvores e imagens sintéticas: adição com sessão aberta, reinício, pasta vazia,
subpastas inicialmente vazias, idempotência, raiz substituída, raiz indisponível, pausa antes de
anotar e arquivo de âncoras inseguro. O smoke Electron adiciona um JPEG durante a execução sem
nova seleção nem atualização manual e verifica o catálogo. Teste manual: adicionar uma imagem
à pasta registrada, aguardar a checagem e repetir com o aplicativo fechado.
