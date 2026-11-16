# Subpastas, abertura e Calendário — 2026-11-13

Base: `944d789`, branch `feat/desktop-viewer-and-annotations`, no mesmo checkout do VS Code.
As alterações estão no working tree, sem commit, push ou integração. Este relatório registra
as correções de abertura, navegação e atualização após excluir uma subpasta inteira.

## Correção final: exclusão de uma subpasta inteira

A consulta somente leitura confirmou que o monitor havia registrado `missing` para as duas
ocorrências de `teste/` e para os dois registros históricos da pasta pai. O problema não era
uma exclusão física ignorada: a galeria continuava consultando os registros históricos, as
miniaturas e Propriedades não eram invalidadas ao atualizar, e **Atualizar pastas agora** não
publicava uma atualização da tela quando a revisão do catálogo permanecia igual.

Agora o desktop aplica `exclude_missing=true` antes da paginação em todas as consultas da
galeria, inclusive retry, e nas contagens do Calendário. Só ficam ocultos Assets cujas ocorrências
estão todas confirmadas ausentes em raízes disponíveis. Offline, sem localização, movimento
candidato e ocorrências sobreviventes não são tratados como exclusão. A política é compartilhada
entre galeria e calendário; o cursor é vinculado a esse filtro. Não há migração nem exclusão
de Assets, metadata, favoritos, anotações ou vínculos de álbum. Leituras Python históricas
continuam disponíveis com `exclude_missing=false`, que é o padrão da API interna.

O botão de atualização força uma nova consulta mesmo sem revisão nova. Eventos de atualização
renovam miniaturas e Propriedades. A miniatura anterior deixa de ser usada ao mudar o estado
da ocorrência. Se a seleção desapareceu da página, ela só é limpa depois de confirmar, pelos
detalhes, que todas as suas localizações estão ausentes em raízes disponíveis; uma falha de
consulta ou arquivo offline não prova ausência. O visualizador aberto mantém o comportamento
aprovado, sem resolver outra foto por nome/hash.

A regressão sintética importa somente a pasta pai, cria uma filha e uma neta, depois exclui a
árvore `teste/` inteira sem adicionar nenhum outro arquivo. A galeria, o Calendário e a
navegação de pastas removem essas ocorrências automaticamente. Atualizar manualmente quando o
catálogo já está correto também remonta as miniaturas sem inventar uma nova revisão. Um arquivo
sobrevivente mantém bytes/mtime; detalhes dos Assets ausentes continuam disponíveis no catálogo.
Os testes Python cobrem exclusão automática/manual, metadados de captura e preservação de
favoritos e álbuns, além do retorno de uma ocorrência com a mesma identidade física.

Na cópia mais recente da biblioteca pessoal, a validação Electron confirmou **13 fotos visíveis**
na Biblioteca, no Calendário e na raiz; **quatro registros ausentes** foram preservados fora da
galeria. A pasta `teste` removida deixou de aparecer e a nova subpasta existente foi preservada.
O catálogo continha 17 Assets nessa fotografia do estado, incluindo os quatro históricos.
A origem foi aberta somente para leitura; a execução usou cópia e perfil temporários.


## Diagnóstico anterior: abertura e navegação

A consulta somente leitura à biblioteca configurada identificou exatamente a posição do print:

| Posição na Biblioteca original | Ocorrência | Estado |
| --- | --- | --- |
| 12 | `WP12-LM-purple (2).png` | indisponível |
| 13 | `WP12-LM-purple (2)-rotacionada.png` | indisponível |
| 14 | `teste/WP12-LM-purple (2)-rotacionada.png` | disponível |
| 15 | `teste/WP12-LM-purple (2).png` | disponível |

O caminho do clique por UUID estava correto, mas o botão e o duplo clique permitiam abrir
registros já indisponíveis, e a sequência do visualizador também os incluía. Isso reproduziu
**Prévia indisponível** para a posição **12 de 15**. A abertura desses cartões agora é desabilitada;
a sequência e o carrossel incluem somente fotos disponíveis, também ao buscar páginas adicionais.
Os registros continuam no catálogo; ausências confirmadas ficam fora da galeria normal. Não se abre outro
Asset por semelhança de nome ou hash. Um arquivo que muda fisicamente depois de montar a
sequência ainda pode falhar na leitura; permanecem as proteções e o retry existentes.

A importação e o monitoramento já eram recursivos. Entretanto, a tela **Pastas → pasta pai**
enviava `folder_path=""`, restringindo a consulta a filhos imediatos. Agora envia somente o UUID
da raiz, incluindo imagens de todos os descendentes antes da paginação. O backend devolve também
as subpastas navegáveis nessa consulta. Ao entrar numa subpasta, o filtro de filhos imediatos
permanece. Basta adicionar a pasta pai uma vez, inclusive para novas filhas e netas.

O Calendário tinha duas dificuldades de apresentação: uma biblioteca somente com fotos sem
captura mostrava uma área de anos vazia, e abrir um período ou Sem data saía do modo Calendário.
Agora, quando não existem anos mas há itens sem captura, abre automaticamente **Sem data de
captura** com as fotos visíveis e uma explicação. A galeria de um dia e a galeria Sem data mantêm
Calendário ativo, com **Todos os anos** e **Limpar período**. Uma biblioteca vazia mantém o estado
vazio. Não se atribui data de modificação ou catalogação como captura.

Na biblioteca atual, os 15 Assets não têm captura selecionada nem observações
`DateTimeOriginal`/`DateTimeDigitized` no catálogo. A leitura confinada dos 13 arquivos disponíveis
na investigação anterior também não encontrou esses campos; os dois indisponíveis não puderam
ser inspecionados fisicamente. A ausência de anos é esperada para esses dados. Não houve falha
confirmada de extração/persistência de captura: um JPEG sintético com EXIF aparece no dia correto.

O layout, os comandos do menu de contexto, a interação do carrossel e o componente do visualizador
aprovado foram preservados. Nenhum original, sidecar, registro, anotação ou identidade foi
modificado para resolver a falha. Não há migração, dependência nova ou fusão de homônimos.

## Evidências de abertura antes da exclusão da subpasta

O catálogo pessoal foi aberto somente para leitura e copiado por backup SQLite para um catálogo
com perfil temporário. O Electron deste checkout usou main, preload, renderer e backend reais na
sessão KDE/Wayland. A configuração pessoal não foi trocada. Na etapa anterior à exclusão, após corrigir a abertura e a navegação:

| Visão | Evidência |
| --- | --- |
| Biblioteca | As duas imagens de `teste/` abriram; a sequência continha 13 fotos disponíveis |
| Pastas → wip12-wallpaper | As duas imagens de `teste/` apareceram na página da pasta pai e abriram |
| Pastas → wip12-wallpaper → teste | As duas imagens apareceram e abriram, com sequência de duas fotos |
| Calendário | Abriu automaticamente as 15 fotos em Sem data de captura, com Calendário ativo |

Nas seis aberturas, a imagem decodificada correspondeu à prévia do UUID clicado. Propriedades e
**Localização completa…** resolveram a raiz cadastrada seguida do caminho `teste/` correto.
Nessa etapa, os botões dos dois registros indisponíveis estavam desabilitados; a correção final
acima também os retira da galeria normal. A descrição nativa do caminho
foi interceptada para conferir seu argumento e fechar sem abrir o gerenciador de arquivos.
Diálogos nativos ainda exigem validação manual; caminhos absolutos privados e mídia pessoal não
fazem parte dos testes de regressão nem deste relatório. A cópia temporária é removida ao concluir.

## Testes e validação final

- Python: homônimos com bytes iguais/diferentes permanecem Assets independentes; pai ausente;
  consultas globais, da raiz e da subpasta; miniatura/prévia decodificadas com pixels esperados;
  caminho revelado correto; consultas não alteram catálogo, bytes ou mtime.
- Monitor: uma única raiz descobre JPEG com captura e PNG numa nova `teste/filha/` por eventos,
  sem reseleção nem checagem periódica; reabrir descobre outra imagem adicionada enquanto fechado;
  captura e originais permanecem corretos.
- Renderer: botão e duplo clique não abrem itens indisponíveis/offline/sem localização; sequência
  e novas páginas pulam esses itens; raiz inclui descendentes; Calendário sem anos mostra fotos
  automaticamente; dia/Sem data permanecem no modo Calendário; retorno a Todos os anos.
- Smoke Electron sintético: adiciona somente a pasta pai, primeiro com dois PNGs; confere Calendário
  sem anos; cria JPEG e nova neta durante a execução; ambos são descobertos sem outra seleção;
  confere raiz/subpasta, pixels, UUID, caminho, JPEG em 2024 → Fevereiro → 29, PNGs em Sem data,
  navegação e preservação dos originais. Seleção e descrição nativas são fixtures.

Resultado final: **PASS**.

| Comando executado | Resultado |
| --- | --- |
| `uv sync --locked` | PASS |
| `uv run pytest` | PASS — 721 testes |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS — 178 arquivos |
| `git diff --check` | PASS |
| `git diff --no-index --check /dev/null -- <arquivo>` para cada não rastreado | PASS — política de ausência, smoke, relatório e `index.html` preexistente |
| `pnpm --dir desktop install --frozen-lockfile` | PASS — dependências já atualizadas, lockfile preservado |
| `pnpm --dir desktop test` | PASS — 191 testes em 26 arquivos |
| `pnpm --dir desktop typecheck` | PASS |
| `pnpm --dir desktop lint` | PASS |
| `env -u ELECTRON_RUN_AS_NODE pnpm --dir desktop smoke:subfolder-calendar` | PASS — inclui build, seleção única, novas descendentes, exclusão total e atualização sem revisão |
| `env -u ELECTRON_RUN_AS_NODE PLAYMEMORIES_DESKTOP_INGESTION_LAB=1 pnpm --dir desktop smoke` | PASS — inclui build, visualizador/menu, rotação, foco e calendário |
| `env -u ELECTRON_RUN_AS_NODE pnpm --dir desktop smoke:demo` | PASS — inclui build, recuperação do backend e preload ausente |

Revisão final: não há mídia, bancos, secrets ou artefatos gerados nas alterações. O `index.html`
não rastreado e preexistente foi preservado. O aviso do pnpm sobre uso de outro store não impediu
a instalação congelada. O smoke demo emite erros IPC ao parar deliberadamente o backend e passa
pelas asserções de recuperação.

Na fase de reprodução, seis
asserções novas falharam na base anterior, expondo a abertura dos ausentes, a exclusão das filhas
na raiz e o estado vazio do Calendário. Duas fixtures antigas de foco usavam fotos sem localização
como se fossem disponíveis; foram ajustadas para representar fotos disponíveis. O ESLint exigiu
explicitar as dependências estáveis do callback do Calendário; isso foi corrigido sem desabilitar
regras. Nesta etapa, a automação sintética inicialmente tentou devolver um elemento DOM pelo
IPC de teste; foi corrigida para devolver um valor clonável. Na conferência da cópia pessoal,
a asserção de ausência de todas as subpastas foi corrigida para exigir somente a ausência de
`teste`, preservando a nova subpasta existente. São ajustes do harness, não remoções de dados.
Os smokes podem emitir mensagens Wayland de cor; as asserções verificam a imagem realmente
decodificada, não apenas a ausência de erro no terminal.

## Como abrir e conferir no KDE

Feche a janela anterior. Na raiz deste checkout, com a branch `feat/desktop-viewer-and-annotations`:

```sh
uv sync --locked
pnpm --dir desktop install --frozen-lockfile
env -u ELECTRON_RUN_AS_NODE \
    -u PLAYMEMORIES_DESKTOP_DEMO \
    -u PLAYMEMORIES_DESKTOP_SMOKE \
    -u PLAYMEMORIES_DESKTOP_MANAGED_SMOKE \
    -u VITE_DEV_SERVER_URL \
    pnpm --dir desktop start
```

`start` compila os arquivos atuais antes de abrir o Electron. Não use o mockup `index.html` da
raiz como entrada do produto e não é necessário trocar de branch ou recriar a biblioteca.

1. Adicione apenas a pasta pai, se ela ainda não estiver cadastrada. Se já estiver, use
   **Atualizar pastas agora**. Não adicione `teste` separadamente.
2. Abra **Pastas → wip12-wallpaper**: as imagens de `teste/` aparecem junto às da raiz.
   Entre também em `teste`, abra as duas fotos e confira **Localização completa…**.
   Registros cuja ausência foi confirmada deixam a galeria; o catálogo conserva o histórico.
3. Abra **Calendário** na biblioteca atual: as fotos aparecem automaticamente no grupo
   **Sem data de captura**. Os PNGs não ganham anos artificiais. Fotos removidas não entram nas contagens.
4. Para repetir a regressão completa sem tocar na biblioteca pessoal:

   ```sh
   env -u ELECTRON_RUN_AS_NODE pnpm --dir desktop smoke:subfolder-calendar
   ```

   O smoke importa um JPEG com `DateTimeOriginal=2024:02:29 23:30:00` e offset `-03:00`,
   verifica ano/mês/dia, a galeria do dia, Todos os anos e os PNGs sem data. Também exclui
   sua própria subpasta sintética e verifica atualização automática/manual. Ele limpa seus
   próprios arquivos temporários e não deixa uma janela de biblioteca de teste aberta.
