# Fechamento da auditoria — Desktop MVP D01R

- Data: 2026-10-28 (America/Sao_Paulo)
- Branch: `feat/desktop-mvp-d01`
- Escopo: correções dos três achados MAJOR da auditoria D01 e hardening solicitado

## Achados encerrados

1. **URI SQLite e read-only.** O path resolvido passa por `Path.as_uri()`, que codifica espaços,
   Unicode e delimitadores reservados como `#` e `?`; `mode=ro` e `PRAGMA query_only` permanecem
   ativos. Testes abrem catálogos sintéticos com esses nomes, rejeitam DDL e confirmam que nenhum
   arquivo colateral foi criado.
2. **Supervisão de processos.** O launcher continua sendo `uv` para preservar o ambiente travado,
   agora com `--offline`. Em POSIX ele inicia um grupo dedicado que contém `uv` e Python; shutdown,
   timeout e falhas sinalizam o grupo, com escalonamento `SIGTERM`/`SIGKILL`. Dependências de spawn
   e tempos são injetáveis para testes determinísticos. O smoke test não deixou bridge ou launcher
   em execução.
3. **Estado e recuperação.** Falhas rejeitam e removem requests pendentes, limpam promise, token,
   buffers e referência do child. Cada geração ignora eventos obsoletos. “Tentar novamente” usa um
   IPC dedicado que encerra a geração anterior, inicia outra e só então repete a consulta.

## Hardening

- stderr é limitado a 4096 caracteres por geração e 512 por linha; controles, valores associados
  a token/secret/password/authorization e paths são redigidos antes do log do processo principal;
- permissões Electron são negadas por padrão nos handlers de check e request;
- CSP de produção usa `connect-src 'none'`; desenvolvimento libera somente o WebSocket HMR em
  `127.0.0.1:5173`; `object-src`, `base-uri` e `form-action` são negados;
- nenhuma dependência, listener HTTP, contrato de domínio ou operação de mídia foi introduzido.

## Evidências executadas

```text
uv sync --locked                                      PASS
uv run pytest                                         PASS (269)
uv run ruff check .                                   PASS
uv run ruff format --check .                          PASS (82 arquivos)
pnpm install --frozen-lockfile                        PASS
pnpm typecheck                                        PASS
pnpm lint                                             PASS
pnpm test                                             PASS (6)
pnpm build                                            PASS
git diff --check                                      PASS
smoke gráfico Arch, encerramento automático           PASS
processos bridge/uv remanescentes após smoke           nenhum
```

Os testes TypeScript reproduzem shutdown normal, timeout de startup, crash com nova geração,
escalonamento de sinais e redação de diagnóstico. Os testes Python reproduzem a ambiguidade de URI
e a tentativa de escrita. D02, empacotamento e suporte Windows/macOS permanecem fora deste escopo.
