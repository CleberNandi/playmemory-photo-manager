---
name: implement-increment
description: Implement a scoped PlayMemories Photo Manager code increment with contract-first changes, tests, validation, and an explicit handoff. Use for product code changes; do not use for review-only or docs-only tasks.
---

# Implement increment

1. Confira branch, HEAD, status, não rastreados e alterações existentes. Confirme a baseline e não
   descarte nem misture trabalho alheio.
2. Leia `AGENTS.md` e somente ADRs, contratos e código diretamente relacionados ao incremento.
   Identifique invariantes, API pública, fora de escopo e critérios de aceite antes de editar.
3. Crie uma branch isolada a partir da base indicada quando a tarefa solicitar. Se base ou estado
   divergirem de modo material, pare e reporte.
4. Implemente a menor mudança que satisfaça o contrato. Reutilize regras de domínio e persistência;
   não introduza migração, dependência, serviço, abstração ou refatoração especulativa.
5. Adicione testes sintéticos para caminho feliz, limites, falhas e invariantes afetados. Não use
   mídia pessoal, serviços externos ou dados reais.
6. Use `$quality-gates` ao terminar. Corrija falhas dentro do escopo e registre qualquer validação
   que não possa ser executada.
7. Entregue resumo de arquivos, API/comportamento, testes executados, riscos e decisões pendentes.
   Crie commit somente quando o usuário autorizar; não faça merge automaticamente.
