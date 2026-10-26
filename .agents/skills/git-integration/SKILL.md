---
name: git-integration
description: Integrate a previously homologated PlayMemories Photo Manager branch into main with a fast-forward-only merge. Use only when the user explicitly authorizes integration; never use for ordinary implementation handoff.
---

# Git integration

Esta skill não concede autorização. Antes de alterar branches:

1. Confirme autorização explícita e homologação prévia da mudança, incluindo os resultados atuais
   de `$quality-gates`.
2. Registre branch, HEAD, alvo, `git status --short --branch`, remotos e arquivos não rastreados.
   Exija working tree limpa e confirme que os commits esperados são exatamente os que serão
   integrados.
3. Verifique ancestralidade com `git merge-base --is-ancestor <target> <source>`. Divergência,
   gates falhos ou homologação ambígua interrompem a integração.
4. Mude para o alvo autorizado e execute exclusivamente:

   ```text
   git switch <target>
   git merge --ff-only <source>
   ```

5. Revalide HEAD, ancestralidade e working tree do alvo. Execute novamente os gates exigidos pela
   homologação quando ela não cobrir exatamente o commit integrado.
6. Preserve a branch de origem. Não faça merge commit, rebase, squash, reset, exclusão de branch,
   criação de remoto ou push.

Reporte hashes anterior/final, comando de integração e validações. Qualquer conflito ou necessidade
de história não fast-forward exige nova decisão do usuário.
