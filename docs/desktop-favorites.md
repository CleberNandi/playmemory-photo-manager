# Favoritos no desktop

## Comportamento

Uma biblioteca real ativa permite marcar/desmarcar favorito no cartão, na tabela de detalhes
ou no topo das propriedades. A escolha é salva exclusivamente na anotação do Asset no catálogo;
originais, sidecars, metadata extraída, identidade e rating permanecem inalterados. Nenhuma
migração ou dependência nova é necessária. Catálogos existentes continuam utilizáveis.

O botão fica desabilitado durante a requisição e só apresenta o novo estado após confirmação.
Perder a resposta não prova rollback: a interface mostra uma mensagem fixa para conferir o
catálogo ao reabrir, sem retry automático. A requisição define true/false explicitamente, em vez
de alternar o valor no servidor; repetir o mesmo valor não alterna o favorito nem duplica a
anotação. Respostas de outra sessão ou após desmontagem não atualizam a biblioteca atual.

Favoritos, tanto na navegação quanto na caixa da barra central, passa a consultar todo o catálogo
com paginação no backend. A consulta pode ser combinada com o período de captura selecionado.
Texto e pastas continuam filtros locais dos itens carregados. O cursor incorpora o filtro de
favoritos; usar o cursor de outra consulta é rejeitado. Remover um favorito na visão filtrada
retira o cartão, e uma lista vazia informa Nenhum favorito encontrado, sem afirmar que todo o
catálogo está vazio. O demo continua somente leitura.

## Fronteiras

- Preload expõe somente `setFavorite(assetId, favorite)`, sem SQL, paths ou invoke genérico.
- IPC `annotation:favorite` usa envelope de sessão, UUID canônico, booleano estrito e allowlist
  exata de campos, além da validação do remetente já existente.
- Python `annotation.favorite` valida a sessão ativa e reaproveita `Catalog.set_favorite` em
  conexão de comando própria do lifecycle. Não há observação da mídia nesta operação.
- Preparação/aplicação em execução bloqueia o comando com busy. A transação é curta e preserva
  o limite de espera SQLite do lifecycle. Resultado não confirmado é público como outcome_unknown.
- `gallery.list` recebe `favorites_only` booleano. A consulta é somente leitura e não usa a
  primeira página da interface como universo dos favoritos.

## Roteiro manual

1. Abra seu catálogo existente; não precisa recriá-lo nem catalogar as fotos novamente.
2. Use ☆ Favoritar em duas imagens; a confirmação deve mudar para ★ Favorito.
3. Abra uma das imagens nas propriedades e confira a mesma marcação.
4. Entre em Favoritos. Remova uma das marcações e confira que o cartão sai da lista.
5. Volte à Biblioteca; a imagem deve continuar catalogada, apenas sem a estrela.
6. Feche e reabra o mesmo catálogo e confira a persistência da outra marcação.

Use a mesma execução de laboratório já documentada em [Imagens e calendário](desktop-media-calendar.md).
Os testes usam apenas catálogos e imagens sintéticos.

## Validação

A suíte cobre booleanos inválidos, campos extras e paths, sessão expirada, Asset inexistente,
catálogo bloqueado sem retry, preservação das demais anotações, persistência/reabertura, favoritos
além da primeira página e paginação sem duplicatas. Frontend cobre duplo clique durante salvamento,
resposta perdida, mensagem sanitizada, resposta de outro Asset e descarte após desmontagem.
O smoke Electron real cobre marcar, consultar o filtro global e desmarcar.

Gates executados: `uv sync --locked`, 670 testes Python, Ruff e formatação, whitespace incluindo
arquivos novos; 126 testes desktop em 20 arquivos, typecheck, ESLint e build. Os smokes Electron
laboratório e demo passaram, incluindo a barra fixa e as funções anteriores de imagens/calendário.
Diálogos nativos KDE continuam sujeitos à homologação manual; favoritar não exige diálogo nativo.
