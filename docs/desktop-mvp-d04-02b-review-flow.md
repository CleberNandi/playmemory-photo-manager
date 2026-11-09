# D04-02B — Revisão e catalogação no desktop

## Entrega testável

O laboratório conecta preparação, revisão paginada, seleção explícita de até 100 candidatos,
confirmação nativa, aplicação e atualização da biblioteca. A branch inclui os incrementos
anteriores de autorização, preflight, aplicação transacional e registro de comandos.
Não requer mudança de schema nem novas dependências.

Apenas candidatos marcados `selectable` podem ser selecionados. JPEG estruturalmente válido
não implica elegibilidade: ocorrências já conhecidas ficam indisponíveis. A seleção permanece
entre páginas. Depois de aplicar um lote, prepare outra proposta para continuar.

## Fronteiras e falhas

- IPC tipado: `ingestion:apply` e `ingestion:application-status`; o renderer envia IDs, nunca paths.
- O processo main gera a chave idempotente e confirma quantidade e catálogo em diálogo nativo,
  com Cancelar como padrão. Cancelar preserva a seleção sem escrever no catálogo.
- O supervisor reutiliza limites, protocolo e encerramento/reap da preparação. A proposta privada
  passa por memfd anônimo selado; a inspeção e a escrita SQLite ocorrem em processo separado.
- A aplicação revalida a autorização e o snapshot na transação. Preserva UUIDs lógicos, originais
  e sidecars; hash não autoriza união de Assets.
- Falha de transporte ou resultado indeterminado não dispara retry automático. A interface exige
  reabrir a biblioteca para reconciliar o estado. Fechar aguarda o encerramento real do worker.
- A galeria só é atualizada após resultado aplicado; respostas antigas de paginação são descartadas.

## Como testar

Inicie na raiz do checkout:

```sh
pnpm --dir desktop install --frozen-lockfile
PLAYMEMORIES_DESKTOP_LIBRARY_LAB=1 PLAYMEMORIES_DESKTOP_INGESTION_LAB=1 pnpm --dir desktop start
```

1. Em Arquivo, crie ou abra um catálogo fora da pasta de mídia.
2. Use Adicionar pastas, escolha uma árvore de teste com JPEGs e prepare a proposta.
3. Abra a proposta, selecione um subconjunto e use Catalogar selecionados.
4. Cancele a confirmação primeiro: a seleção deve continuar disponível, sem novos itens.
5. Repita e confirme. Confira o resultado e use Ver itens na biblioteca; selecione um item
   para consultar suas propriedades.
6. Feche e abra o mesmo catálogo, inclusive após reiniciar o app. Os itens devem persistir.
   Prepare novamente a mesma pasta: ocorrências conhecidas não devem ser selecionáveis.

O laboratório usa preferências temporárias; após reiniciar, abra o catálogo explicitamente.
O modo demo não habilita escrita. Use arquivos de estudo, não mídia pessoal, para homologação.

## Validação e limites

- Python: 637 testes; Ruff e formatação aprovados.
- Desktop: 114 testes em 18 arquivos; typecheck, ESLint e build aprovados.
- Electron headless: fluxo real de preparação/revisão/seleção/aplicação/galeria/propriedades,
  com JPEGs sintéticos e confirmação de originais inalterados; demo também aprovado.
- Harness de navegador conectado ao backend Python real: fluxo completo e larguras de
  1180, 800 e 760 pixels, sem overflow horizontal.

Os harnesses substituem os diálogos nativos por escolhas sintéticas; confirmação e cancelamento
no KDE ainda dependem do teste manual. Os cartões já representam itens reais do catálogo, mas
miniaturas reais, zoom e visualização ampliada ainda não fazem parte desta entrega.
