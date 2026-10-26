# Instruções para agentes

## Projeto e autoridade

O PlayMemories Photo Manager é um produto local-first para catalogar e organizar mídia sem
alterar originais por padrão. ADRs aceitas em `docs/adr/` são normativas; para cada tarefa, leia
somente as ADRs e os contratos diretamente relevantes. O prompt corrente pode restringir o
escopo, mas uma exceção arquitetural exige decisão explícita, não inferência.

A arquitetura é um monólito modular: backend e casos de uso em Python, catálogo SQLite e futura
interface em React + TypeScript. Electron é apenas o candidato preferencial ao shell, condicionado
à PoC do ADR-004. UI e shell não acessam SQLite ou filesystem contornando os casos de uso.

## Invariantes

- `Asset` possui UUID lógico estável; path, inode e hash não são identidade.
- `FileLocation` representa uma ocorrência de um Asset. Mesmo SHA-256 não autoriza merge.
- Preserve proveniência temporal, metadata extraída, anotações e distinções entre `offline`,
  `missing` e observação física atual.
- Não mover, sobrescrever, excluir nem escrever em originais ou sidecars sem contrato aprovado,
  autorização explícita e proteções auditáveis.
- Testes e exemplos usam apenas bancos, árvores e mídia sintéticos temporários. Não versionar
  fotografias pessoais, catálogos locais, credenciais, paths privados ou artefatos gerados.
- Tratar paths, symlinks, traversal, TOCTOU e erros públicos como fronteiras de segurança; falhar
  fechado quando o confinamento não puder ser demonstrado.

## Trabalho e validação

Preserve alterações existentes e confira branch, status e arquivos não rastreados antes de editar.
Não descartar trabalho, criar remoto, fazer push, commit ou merge sem autorização da tarefa.
Mantenha mudanças pequenas e no escopo; não misture incrementos independentes.

Use as skills locais para procedimentos detalhados:

- `$implement-increment` (`.agents/skills/implement-increment/SKILL.md`) para incrementos de código;
- `$quality-gates` (`.agents/skills/quality-gates/SKILL.md`) para a validação final;
- `$git-integration` (`.agents/skills/git-integration/SKILL.md`) somente quando a integração tiver
  sido autorizada e homologada.

`$quality-gates` é a referência autoritativa para os comandos de validação. Testes devem cobrir o
comportamento e os invariantes afetados, inclusive falhas e casos adversariais proporcionais ao
risco. Documentação deve refletir contratos reais, separar fato de proposta e registrar limitações
sem duplicar ADRs ou README.
