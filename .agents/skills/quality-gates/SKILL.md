---
name: quality-gates
description: Run and report the PlayMemories Photo Manager validation stack before handoff, commit, or integration. Use when a change must be verified; never declare PASS from prior or reported results alone.
---

# Quality gates

Parta da raiz do repositório e registre resultados reais, inclusive comandos indisponíveis:

1. Inspecione `git status --short --branch` e arquivos não rastreados.
2. Execute, sem omitir falhas:

   ```text
   uv sync --locked
   uv run pytest
   uv run ruff check .
   uv run ruff format --check .
   git diff --check
   ```

   `git diff --check` não examina arquivos não rastreados. Para cada arquivo novo listado por
   `git ls-files --others --exclude-standard`, execute
   `git diff --no-index --check /dev/null -- <arquivo>`. Esse comando não altera o staging; status
   `1` apenas indica que o arquivo difere de `/dev/null`, enquanto mensagens na saída identificam
   erros de whitespace. Status maior que `1` indica falha do comando.
3. Inspecione arquivos alterados e não rastreados. Confirme que o diff não inclui mídia pessoal,
   bancos SQLite, binários/artefatos gerados, credenciais, tokens, secrets ou paths privados de
   dados. Não exponha valores sensíveis no relatório.
4. Compare os testes com os comportamentos e riscos alterados; aprovação mecânica não substitui
   cobertura relevante.
5. Reporte cada comando, status e falha. O resultado é `PASS` somente se todos os gates aplicáveis
   forem realmente executados e aprovados; caso contrário, reporte `FAIL` ou `NOT RUN` com motivo.

Não modifique código ou configuração apenas para esconder uma falha. Correções pertencem ao escopo
da tarefa que acionou esta skill.
