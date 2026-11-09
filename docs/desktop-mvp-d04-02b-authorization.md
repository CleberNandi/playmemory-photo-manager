# D04-02B — autorização do recorte catalogável

Baseline: `22c76ee`. Primeiro incremento de D04-02B, limitado à decisão privada
em memória. Não implementa aplicação, IPC ou interface de revisão.

## Contrato implementado

`authorize_scoped_ingestion(scoped, candidate_ids)` recompõe o recorte pelo
validador já existente e exige igualdade integral antes de admitir a seleção.
Aceita somente uma tupla de até 100 IDs opacos únicos pertencentes aos novos
candidatos elegíveis daquela proposta. JPEG válido de localização já conhecida,
diretórios, excluídos e IDs alheios não recebem nova autorização de criação.

A escolha vazia produz zero seleções, nunca autorização implícita de todos.
A ordem fornecida é normalizada por caminho relativo. `PHOTO` e `image/jpeg`
são atribuídos pelo backend, sem parâmetros de MIME ou kind fornecidos pela UI.
A decisão imutável vincula o fingerprint do recorte completo, run, raiz, IDs e
seleções exatas, com digest canônico da decisão.

`validate_scoped_authorization` recompõe a decisão e exige igualdade antes de
uma futura admissão de escrita. Alterações de IDs, recorte, seleção ou tipagem
invalidam a decisão. O objeto é privado ao backend: **não é uma credencial
assinada**, não prova consentimento humano por si só e não deve ser aceito como
payload pronto vindo do renderer.

## Limites e próximos incrementos

Nenhuma dessas funções consulta arquivos, abre conexão SQLite, grava catálogo
ou altera originais. O contrato legado continua estrito e não recebe uma
proposta artificialmente filtrada. Não há migrações nem dependências novas.

A aplicação futura ainda exige, sob os contratos D04-00 e D04-02A:

1. Revisão humana, confirmação e vinculação à sessão/proposta privada.
2. Grant válido e preflight físico confinado fora da transação, com limites
   honestos de TOCTOU; esta autorização não comprova frescor físico.
3. Recomposição de snapshot/plano/recorte sob o mesmo BEGIN IMMEDIATE que contém
   todas as criações. Conflito em qualquer item bloqueia o lote inteiro.
4. Relatório, deduplicação de clientRequestId e tratamento de outcome_unknown
   sem retry automático; falha de rollback suspende comandos.
5. IPC estreito, UI de seleção e confirmação, e atualização explícita da galeria.

D04-02B permanece parcial. Não há botão novo de aplicação nesta revisão.

## Validação

Testes usam JPEGs, árvores e bancos sintéticos temporários. Cobrem subconjunto,
ordem canônica, escolha vazia, limites de 100/101, IDs duplicados/alheios,
exclusões, diretórios, localização conhecida, alteração de recorte e decisão,
MIME/kind adulterados e preservação byte a byte dos arquivos após autorização.

Resultados: `uv sync --locked`, 576 testes Python (22 novos), Ruff, formatação,
whitespace incluindo novos arquivos, typecheck desktop, 104 testes desktop,
ESLint e build aprovados. As primeiras rodadas revelaram erros nas fixtures
(JPEG de quatro componentes e localização sem atributos observados/conexão
preparada); foram corrigidas usando o perfil JPEG suportado e a API existente,
sem relaxar validadores de produção. Smokes gráficos não se aplicam a esta API
pura; nenhum fluxo novo de UI/IPC está sendo homologado por esses resultados.
