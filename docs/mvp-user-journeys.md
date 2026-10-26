# Jornadas do usuário do MVP

## Legenda

- **Disponível:** backend existente pode sustentar o passo, embora ainda não exista UI.
- **Parcial:** há modelo ou parte do caso de uso, mas falta um contrato necessário.
- **Inexistente:** precisa ser implementado antes de a UI prometer o passo.

As jornadas descrevem o produto desejado; a coluna de capacidade impede confundir proposta de UX
com software já entregue.

## J1 — Abrir o Photo Manager e escolher uma biblioteca

**Intenção:** retomar com segurança a última biblioteca ou escolher outra.

1. Ao abrir, o produto valida a preferência local e tenta abrir o catálogo sem iniciar scan.
2. Se não houver biblioteca, apresenta “Criar biblioteca” e “Abrir biblioteca existente”.
3. Se houver, mostra o conteúdo catalogado e verifica raízes de forma não bloqueante.
4. Catálogo incompatível, corrompido ou sem permissão abre um estado de diagnóstico; nunca é
   migrado, substituído ou recriado silenciosamente.
5. O usuário pode escolher outra biblioteca sem mesclar dados automaticamente.

**Resultado:** uma biblioteca ativa identificável e o estado de cada raiz.

**Capacidade:** inicialização/migração SQLite disponível; lifecycle, seletor, preferências,
backup e recuperação inexistentes.

**Aceite:** cancelar o seletor não cria arquivo; abrir não varre nem altera originais; o nome e o
caminho do catálogo ficam distinguíveis das pastas de fotos.

## J2 — Selecionar uma pasta local e catalogar novas fotografias

**Intenção:** adicionar referências a fotos já existentes sem mover arquivos.

1. Em “Adicionar pasta”, o usuário escolhe uma pasta local e confirma escopo recursivo.
2. O produto rejeita arquivo, symlink/reparse point como raiz ou caminho já registrado de forma
   incompatível; explica o motivo.
3. A análise read-only mostra fase, escopo e progresso; cancelamento preserva resultado parcial
   sem tratá-lo como completo.
4. O plano separa “já catalogadas”, “novas candidatas”, “inconclusivas” e “bloqueadas”.
5. O usuário revisa e seleciona explicitamente candidatas novas.
6. O produto gera autorização ligada ao plano e aplica o lote transacional.
7. Um relatório mostra criadas, já existentes, não aplicadas e conflitos. Reexecução não duplica
   localizações.

**Resultado:** novos Assets e FileLocations; nenhum hash, metadata, thumbnail ou `missing`
implícito.

**Capacidade:** scanner, avaliação, planner, autorização e aplicação disponíveis; job assíncrono,
progresso granular, seletor e mídia elegível parcial/inexistentes.

**Aceite:** nenhuma escrita no acervo; plano parcial não conclui ausência; alteração entre plano e
aplicação gera conflito e rollback conforme contrato; seleção vazia não cria itens.

## J3 — Navegar por pastas

**Intenção:** ver a biblioteca conforme sua organização física.

1. O usuário abre “Pastas” e escolhe uma raiz.
2. A árvore carrega níveis sob demanda; contagens distinguem total catalogado de disponível.
3. Selecionar pasta atualiza a galeria sem criar uma tela paralela.
4. Subpastas podem ser incluídas/excluídas do recorte de modo explícito.
5. Raiz offline mantém a árvore catalogada, mas marca conteúdo que exige arquivo como indisponível.

**Capacidade:** raiz/localização e paginação básica disponíveis; árvore, contagens e query por
subárvore inexistentes.

**Aceite:** caminho exibido deriva da raiz + relativo; nunca é identidade do Asset; pasta vazia,
offline e sem resultados filtrados são estados diferentes.

## J4 — Navegar por datas

**Intenção:** reencontrar fotos no tempo sem perder a proveniência.

1. O usuário abre “Datas”; a navegação oferece anos/meses/dias apenas onde houver projeção.
2. Selecionar período filtra a mesma galeria e preserva ordenação estável.
3. “Data desconhecida” reúne itens sem projeção escolhida.
4. O painel de detalhes informa valor, precisão, timezone/ausência dele e fonte.

**Capacidade:** schema temporal disponível; extração, projeção durante ingestão, consultas e
timeline inexistentes.

**Aceite:** mtime não aparece como captura sem rótulo; tempo flutuante não ganha UTC presumido;
mudança de filtro não altera metadata.

## J5 — Visualizar uma fotografia e inspecionar detalhes

**Intenção:** examinar conteúdo e contexto sem editar o original.

1. Enter ou duplo clique abre o visualizador sobre a seleção atual.
2. A imagem usa preview progressivo; zoom, ajustar à janela e 100% não recarregam a biblioteca.
3. Setas anterior/próximo percorrem o resultado corrente, não toda a biblioteca.
4. O painel de detalhes mostra anotações, data/proveniência, propriedades técnicas, Asset e todas
   as FileLocations; dados ausentes aparecem como “Não disponível”.
5. Falha de decoder preserva detalhes e permite localizar o arquivo.

**Capacidade:** entidades persistidas parcialmente disponíveis; decoder, loader, metadata e UI
inexistentes.

**Aceite:** arquivo offline/ausente/não decodificável são distintos; zoom não escreve arquivo;
caminhos sensíveis não vazam em logs de interface.

## J6 — Selecionar várias fotos

**Intenção:** organizar um conjunto previsível e reversível no catálogo.

1. Clique seleciona uma; Ctrl/Cmd alterna; Shift estende intervalo; Espaço alterna o item focado.
2. A barra contextual informa quantidade e escopo do resultado.
3. “Selecionar tudo” pergunta implicitamente pelo escopo através do rótulo: página visível ou
   todos os resultados; filtros posteriores não ampliam silenciosamente a seleção.
4. O usuário adiciona/remove álbum ou tag; confirmação resume a mudança virtual.

**Capacidade:** associações unitárias disponíveis; seleção no cliente e comandos em lote
inexistentes.

**Aceite:** rolagem virtualizada não perde seleção; ação informa falhas parciais ou é atômica;
nenhum comando move arquivos.

## J7 — Organizar por álbuns e tags

**Intenção:** criar organização independente do filesystem.

1. Em “Álbuns”, o usuário cria um álbum com nome e descrição opcionais.
2. A partir da galeria ou do álbum, adiciona/remove a seleção.
3. Em “Tags”, cria/reutiliza tags; variações normalizadas não criam duplicata silenciosa.
4. O painel de detalhes permite editar associações do item atual.

**Capacidade:** criação/listagem e associações disponíveis; renomear/excluir entidades, comandos em
lote e UI inexistentes ou não contratados.

**Aceite:** Asset pode estar em vários álbuns e ter várias tags; associação repetida é idempotente
quando previsto; remover associação não remove Asset/FileLocation.

## J8 — Buscar e filtrar

**Intenção:** reduzir o conjunto sem aprender onde o arquivo está.

1. Busca e filtros ficam no cabeçalho da galeria em qualquer perspectiva.
2. Texto procura apenas campos indexados e declarados; filtros disponíveis refletem dados reais.
3. Chips mostram filtros ativos; “Limpar” volta ao contexto anterior.
4. Zero resultados preserva consulta e oferece remoção de filtros, não “biblioteca vazia”.

**Capacidade:** inexistente; schema fornece alguns campos, mas não há FTS/API combinatória.

**Aceite:** consulta cancelável, resultados paginados e ordenados; filtros indisponíveis não são
mostrados; busca não abre arquivos do acervo.

## J9 — Iniciar análise de duplicatas exatas

**Intenção:** localizar ocorrências byte a byte iguais sem alterar o acervo.

1. Em “Ferramentas > Duplicatas exatas”, o usuário escolhe raízes/pastas catalogadas e extensões
   suportadas explicitamente.
2. Uma confirmação explica que conteúdo será lido para SHA-256 e que nenhuma ação em arquivos
   será executada.
3. O job pré-filtra por tamanho, calcula hashes dos candidatos e detecta mudanças observáveis.
4. Progresso informa fase, arquivos considerados, bytes lidos quando mensurável, falhas e
   cancelamento.
5. O resultado abre a revisão ou informa que nenhum grupo foi encontrado.

**Capacidade:** inexistente no produto; comprovada no handoff externo para extensões configuradas.

**Aceite:** só igualdade SHA-256 após tamanho igual forma grupo; arquivos únicos não são marcados;
cancelamento não produz conclusão completa; saída não certifica que bytes formam imagem válida.

## J10 — Revisar um grupo e escolher o que preservar

**Intenção:** entender todas as consequências antes de registrar uma decisão.

1. A lista resume grupos, membros, bytes redundantes estimados, estado e decisão pendente.
2. Abrir grupo mostra os membros lado a lado ou em lista sincronizada, sem esconder os demais.
3. Cada membro mostra thumbnail/fallback, caminho relativo + raiz, disponibilidade, tamanho,
   Asset relacionado, todas as FileLocations desse Asset, proteção, hardlink e dependências.
4. O usuário marca uma ocorrência para preservar. Isso não funde Assets.
5. Um motivo não vazio é obrigatório; a interface registra que a escolha é humana.
6. Membro alterado, protegido, offline ou com dependência mantém o grupo bloqueado conforme regra,
   mesmo após uma escolha.

**Capacidade:** modelos de catálogo e handoff separados; integração inexistente.

**Aceite:** exatamente um `keep` por grupo decidido; todos os membros continuam visíveis; o mesmo
digest não apaga anotações nem colapsa identidades; thumbnail inválida não invalida igualdade.

## J11 — Revisar plano dry-run sem executá-lo

**Intenção:** inspecionar uma proposta estática e seus bloqueios.

1. “Gerar plano de revisão” cria um artefato versionado com snapshot, escolhas, motivos,
   candidatos teóricos, protegidos e bloqueios.
2. A tela de resumo mostra claramente “Plano não executável”. Não há botão Executar.
3. O usuário navega por grupos prontos, pendentes, bloqueados e desatualizados.
4. “Revalidar” relê evidências e compara com o plano sem modificá-lo.
5. Se qualquer membro mudou, o plano fica desatualizado e a ação disponível é “Analisar
   novamente”.

**Resultado:** plano local com `action_authorized=false` e `operations_performed=false`.

**Capacidade:** demonstrada no Duplicate Lab, inexistente no produto.

**Aceite:** plano bloqueado pode ser revisado, jamais executado; checksum é rotulado como
integridade acidental; destino proposto não é criado; nenhuma linguagem promete recuperação.

## Critérios transversais

- Toda jornada longa tem estado inicial, execução, cancelamento, falha recuperável e resumo.
- Foco retorna ao elemento que abriu modal/painel; mensagens e progresso são acessíveis.
- Atualização externa nunca é convertida silenciosamente em sucesso, `missing` ou decisão.
- Todos os testes de UX usam dados sintéticos e cobrem milhares de itens por geração controlada.
- Logs e relatórios sanitizam caminhos quando compartilhados; artefatos com caminhos ou
  thumbnails são privados por padrão.

## Questões para validação com usuários

- Usuários pensam primeiro em pasta, data ou busca ao retomar uma biblioteca?
- “Biblioteca” é compreendida como arquivo de catálogo + raízes, ou exige outro termo?
- Na seleção total, a distinção entre itens carregados e todos os resultados é clara?
- Quais fatos tornam uma ocorrência preferível para preservar sem transformar heurística em
  escolha automática?
- Comparação de membros funciona melhor em cards, tabela ou foco alternado para grupos grandes?
