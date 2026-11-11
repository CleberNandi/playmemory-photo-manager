# Biblioteca principal e adição direta de pastas

Status: implementado no desktop. O pedido de carregar a pasta escolhida autoriza a catalogação
de suas imagens aceitas, sem confirmação por arquivo. O acompanhamento de novas imagens está
descrito em [Monitoramento de pastas](desktop-folder-monitor.md).

## Comportamento normal

- Iniciar o aplicativo abre automaticamente a última biblioteca persistida. Sem uma seleção
  anterior, abre ou cria `library-state/principal.sqlite3` no perfil privado do aplicativo,
  apresentada como **Minha biblioteca**. O usuário não precisa escolher um arquivo SQLite.
- A criação é exclusiva e só ocorre depois de `library.open` responder `not_found`. Corrupção,
  versão incompatível ou falta de permissão não provocam recriação nem sobrescrita do catálogo.
- **Adicionar pastas** abre diretamente o seletor nativo de diretórios. Confirmar a seleção inicia
  a leitura recursiva e o registro das imagens aceitas. Cancelar não inicia preparação nem gravação.
- A interface mostra andamento, quantidade adicionada e interrupções; ao terminar, atualiza a
  galeria. Não exige **Preparar proposta**, revisão de candidatos ou confirmação de cada lote.
- Repetir a mesma pasta não duplica ocorrências já conhecidas. Não é deduplicação por hash nem
  merge de Assets. Favoritos e anotações continuam no catálogo, separados dos originais.
- Abrir/criar outra biblioteca e a preparação manual continuam disponíveis nos menus. Uma
  biblioteca externa escolhida anteriormente continua preferida e é reaberta automaticamente,
  mesmo que a antiga opção de reabertura estivesse desmarcada. Não há migração ou cópia silenciosa.

O perfil normal agora é persistente inclusive com as flags de laboratório. Apenas demonstração
ou `PLAYMEMORIES_DESKTOP_SMOKE=1` usam diretórios temporários removidos ao sair. Dados de antigos
perfis temporários não podem ser recuperados por esta mudança. Se o catálogo preferido responder `not_found`, o aplicativo abre ou cria a biblioteca principal
automaticamente, sem recriar o arquivo externo apagado. Isso não recupera imagens ou anotações
do catálogo removido. Para outros erros (corrupção, permissão, incompatibilidade), informa a falha
e permite abrir outro ou usar a biblioteca principal, sem sobrescrever o arquivo indisponível.

## Fronteiras e limites

O main resolve o destino físico da seleção e prende sua identidade `dev/ino` durante o trabalho.
Antes de cada lote confere a mesma raiz e a sessão ativa. Paths não chegam ao renderer. O backend
Python continua responsável por concessões, enumeração, verificação, IDs, transações e SQLite.
Não há escrita em originais ou sidecars, nem mudança de schema ou dependências.

A preparação existente continua internamente: cada passagem usa uma concessão nova de uso único,
lista candidatos em páginas de 50 e aplica no máximo 100 IDs escolhidos. Cada transação mantém as
verificações existentes. A mesma seleção nativa autoriza as passagens deste trabalho. O acompanhamento posterior usa concessões independentes para as raízes
registradas, conforme o contrato de monitoramento. Links internos, sobreposição de catálogo/cache e alterações físicas
continuam sujeitos aos bloqueios do backend.

Os limites existentes permanecem: até 2.000 entradas por preparação, limites de recursos do
worker e históricos/concessões limitados por sessão. Há no máximo 21 passagens por carga e
espera limitada por operação. Uma pasta que exceda esses limites deve ser dividida em subpastas.
Lotes anteriores já concluídos permanecem no catálogo se um posterior falhar. **Parar carga**
interrompe a preparação ou para depois da transação atual; não desfaz lotes concluídos.

Uma resposta perdida na aplicação é tratada como resultado desconhecido, sem repetição automática.
É necessário reabrir a biblioteca para conferir o resultado. Uma nova seleção enquanto a carga
estiver ativa se conecta ao mesmo trabalho e não abre outro diálogo. Trocas de biblioteca ficam
bloqueadas durante a carga; encerramento/falha da sessão invalida respostas antigas.

Há checagem periódica de novas imagens nas pastas registradas, inclusive ao reabrir a biblioteca.
Ainda não há reconciliação automática de arquivos alterados, removidos ou movidos, nem suporte
universal a codecs. Consulte o contrato de monitoramento para limites e falhas.

## Validação e teste manual

Executar normalmente, sem flags de laboratório:

```sh
uv sync --locked
pnpm --dir desktop start
```

1. Confirmar que uma biblioteca está ativa sem escolher um catálogo.
2. Clicar **Adicionar pastas**, escolher uma pasta sintética pequena e aguardar as miniaturas.
3. Marcar favorito, fechar e reiniciar o aplicativo; verificar a biblioteca e o favorito.
4. Adicionar a mesma pasta novamente e verificar que nenhuma ocorrência foi duplicada.
5. Cancelar o seletor e conferir que a biblioteca permanece intacta.

Testes automatizados cobrem bootstrap sem catálogo, abertura sem recriação, erro de corrupção,
cancelamento, sessão antiga, seleção repetida, substituição da raiz e resposta perdida. O smoke
Electron com backend real usa 125 JPEGs sintéticos em dois lotes, reabre o catálogo após reiniciar
o backend, verifica favorito persistido e bytes originais inalterados. Diálogos nativos reais
KDE e reinício de dois processos Electron continuam como validação manual; o smoke injeta apenas
a seleção de caminhos de suas próprias fixtures temporárias.
