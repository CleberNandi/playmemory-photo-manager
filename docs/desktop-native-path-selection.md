# Seleção nativa: destino físico explícito

Base de conteúdo: main `49a31db`. Correção motivada pelo smoke manual KDE:
catálogo criado pelo caminho físico, mas seleção de raiz falhando com erro genérico.

## Diagnóstico e mudança

O diálogo pode retornar pasta com barra final. `validPath` em Node a admite, mas
`root_grants._path` exige igualdade com `str(Path(raw))`, que remove a barra final:
`/tmp/media/` resulta em `invalid_request`. A UI não tinha mensagem para esse código.
Essa incompatibilidade foi reproduzida isoladamente; o payload exato da sessão KDE
não foi capturado, portanto a confirmação causal final depende de repetir o smoke.

Main resolve seleções nativas existentes por `realpath`. Para criar catálogo,
resolve somente o pai e preserva o nome final, mantendo a criação exclusiva Python
(sem sobrescrever arquivo ou seguir link no nome final). Cancelamento não chama
Python. Caminhos resolvidos não são enviados pelo renderer.

A confirmação de criação/seleção de raiz exibe seleção e destino físico antes do
consentimento. Um alias como Workspace é aceito como entrada no diálogo; catálogo e
raiz usam exclusivamente o destino físico. Não persistimos o alias, não detectamos
seu redirecionamento posterior e não o seguimos novamente durante a operação.

Isso substitui a proibição de aliases na ENTRADA do diálogo por resolução explícita
no main. O contrato Python permanece estrito: ancestrais sem links, identidade por
descritores, revalidação independente, sobreposição física/léxica, proteção de
catálogo/cache, concessão de uso único. Links internos à mídia continuam excluídos.
`realpath` não substitui nem comprova essas validações. Seleção/FS continuam síncronos
no sentido de aguardar I/O sem deadline específico, limitação preexistente.

UI passa a explicar `invalid_request` e `not_found`, aceitando mensagens de erro
serializadas em objeto ou string sem renderizar conteúdo arbitrário como HTML.

## Validação e pendências

Testes sintéticos verificam pasta com barra final, alias ancestral, criação com pai
alias, alias quebrado e recusa de path relativo. Repetir smoke KDE com catálogo e
mídia irmãos, incluindo seleção via alias e via destino físico. Nenhum Asset ou
FileLocation é criado por este incremento. Auditoria e merge pendentes.
