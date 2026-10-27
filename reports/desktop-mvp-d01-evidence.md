# Evidência de execução — Desktop MVP D01

- Data: 2026-10-27 (America/Sao_Paulo)
- Host: Arch Linux, kernel `7.2.11-arch1-1`, x86_64
- Runtime: Node.js `24.22.1`, pnpm `12.15.0`, uv `0.13.6`, Electron `45.0.0`
- Branch/base: `feat/desktop-mvp-d01` sobre `main` em `5e9a0e0`

## Execução desktop

Comando de smoke test, usando o display gráfico da sessão e encerramento automático exclusivo para
evidência:

```bash
env -u ELECTRON_RUN_AS_NODE \
  PLAYMEMORIES_DESKTOP_SMOKE_EXIT_MS=1500 \
  pnpm start
```

Resultado: status `0`, build Vite concluído, janela criada e log
`PlayMemories desktop ready (local backend supervised)`. O encerramento passou pelo lifecycle do
shell e concluiu o backend Python. A execução precisou ocorrer fora do sandbox do agente porque o
sandbox host do Chromium não pode iniciar dentro dele; o renderer permaneceu com `sandbox: true`,
`contextIsolation: true` e `nodeIntegration: false`.

## Validação

```text
uv sync --locked                                      PASS
uv run pytest                                         PASS (267)
uv run ruff check .                                   PASS
uv run ruff format --check .                          PASS (81 arquivos)
pnpm install --frozen-lockfile                        PASS
pnpm typecheck                                        PASS
pnpm lint                                             PASS
pnpm test                                             PASS (2)
pnpm build                                            PASS
git diff --check + arquivos novos                     PASS
```

Não foram medidos startup, memória ou empacotamento; esses critérios continuam abertos para a
homologação mais ampla prevista no ADR-004. Nenhum suporte a D02–D06 é alegado por esta evidência.
