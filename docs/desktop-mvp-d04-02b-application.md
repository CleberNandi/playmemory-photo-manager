# D04-02B — aplicação atômica do recorte

Base: PR #22 (`564f4e8`), dependente do PR #21. Incremento do caso de uso
Python; ainda não expõe comando IPC nem botão de aplicação na interface.

## Contrato implementado

`apply_scoped_ingestion(catalog, scoped, authorization, expected_root_mount=...)`
valida a proposta privada e a autorização exata. Ausência de autorização, seleção
vazia ou autorização alterada não fazem I/O de mídia nem iniciam escrita. Uma
transação já aberta pelo chamador é rejeitada sem rollback dessa transação.

O preflight dos selecionados ocorre antes de BEGIN IMMEDIATE. Após adquirir a
transação de escrita, um callback privado do núcleo de registro:

1. Revalida a raiz física retida e sua montagem atual.
2. Lê snapshot limitado na **mesma conexão/transação** dos INSERTs, sem abrir um
   segundo leitor. Preserva limites de 2000 localizações e 8 MiB, inclusive limite
   SQLite por valor, restaurando o limite anterior da conexão ao concluir.
3. Recompõe avaliação/plano/recorte a partir das evidências originais e snapshot
   corrente, exigindo igualdade integral com a proposta revisada.
4. Revalida autorização e raiz novamente antes das criações.

O núcleo transacional já existente cria Assets e FileLocations juntos. Não se
chama `apply_ingestion` com um plano filtrado e não se flexibiliza o aplicador
legado. O novo callback é privado/opcional e roda dentro da transação; chamadores
legados preservam o comportamento anterior.

Todos os selecionados são criados ou o lote é revertido. IDs só entram no
relatório depois de commit retornar. O relatório usa `scope_fingerprint` no campo
`plan_fingerprint` para esta API de recorte e inclui candidatos elegíveis novos:
selecionados criados e não selecionados ignorados. Exclusões e localizações já
conhecidas continuam disponíveis na proposta original, sem novas criações.
JPEGs com bytes iguais permanecem Assets independentes; SHA-256 não é promovido.
`last_seen_at` permanece NULL, sem inventar instante de observação por arquivo.

## Conflito, incerteza e recuperação

- Alteração do catálogo após a revisão invalida o lote inteiro. Aplicar novamente
  uma proposta antiga retorna conflito; preparar novamente reconhece caminhos
  conhecidos, sem duplicá-los.
- Falha durante INSERT reverte inclusive pares já criados e Assets ainda sem
  localização; o relatório não devolve IDs de gravação parcial.
- Falha de commit é conservadoramente incerta, mesmo se rollback foi tentado.
  O núcleo marca essa fase em nota interna preservada na cadeia de exceções.
- Falha de rollback ou commit incerto resulta em `TRANSACTION_FAILED` com
  diagnóstico fixo `outcome_unknown`, fecha a conexão de comandos e exige
  recuperação explícita. Nunca presumir zero escritas porque houve exceção:
  um teste simula exceção depois de commit efetivamente persistido.
- O adapter futuro deve descartar a conexão e suspender comandos dessa sessão;
  nenhuma tentativa automática de admissão é autorizada por este resultado.
- Mtime negativo, que o schema não representa, é rejeitado antes de escrita.
  Falhas públicas não expõem paths ou mensagens internas do SQLite.

## Limites e integração pendente

A conexão deve pertencer à biblioteca ativa validada pelo lifecycle. Esta API
privada não substitui isolamento de sessão, grant, política de sobreposição,
deduplicação por clientRequestId, supervisão de processo, revisão humana ou
confirmação nativa. Nenhum desses controles pode ser inferido apenas do digest.
Não há journal durável novo nem migração. Fingerprints/descritores não congelam
bytes contra escritores externos; permanece a limitação física documentada no
preflight. Só a checagem de raiz ocorre na transação, não scan/decodificação.

Próximo incremento: adapter de aplicação com deduplicação/recuperação de resultado
incerto; depois revisão/seleção/confirmar/relatório na UI e refresh da galeria.
D04-02B permanece parcial. Smokes de UI/KDE serão necessários nessa integração.

## Testes

20 testes novos usam bancos/árvores/JPEGs sintéticos: criação de cópias como Assets
independentes, subconjunto, escolha vazia/ausente/adulterada, reexecução, reabertura
por outro leitor, ausência de mídia na transação, writer concorrente bloqueado,
corrida SQLite e de raiz, orçamento de snapshot e restauração de limite, rollback
após primeiro e segundo INSERT Asset, falhas de commit/rollback, erro após commit
efetivo, transação do chamador preservada e mtime negativo.

Validação executada: `uv sync --locked`, 615 testes Python (20 novos), Ruff,
formatação e whitespace incluindo arquivos novos; typecheck desktop, 104 testes,
ESLint e build aprovados. Smokes gráficos deste fluxo ainda não se aplicam: a
integração IPC/UI não foi implementada nem homologada por esses testes.
