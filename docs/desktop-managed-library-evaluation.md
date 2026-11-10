# Biblioteca gerenciada e indexação — avaliação de UX

Status: avaliação arquitetural. A biblioteca principal e a carga ao selecionar uma pasta foram implementadas em [desktop-managed-import.md](desktop-managed-import.md). Monitoramento continua proposto.
Motivação: o usuário confirmou favoritos/imagens e apontou a fricção de criar e selecionar um
arquivo de catálogo antes de navegar pelo acervo.

## Diagnóstico

O problema é expor persistência e etapas técnicas no fluxo principal. O catálogo continua sendo
necessário para UUIDs, favoritos, anotações, datas e operação offline. A existência de um indexador
não elimina esse armazenamento. Um índice de fatos extraídos pode ser reconstruído; favoritos e
anotações do usuário não podem ser tratados como cache descartável.

Referências primárias consultadas em 2026-11-10:

- [digiKam: coleções](https://docs.digikam.org/en/setup_application/collections_settings.html):
  raízes de coleção registradas e opção de monitorar alterações externas para atualizar o banco.
- [darktable: import & review](https://docs.darktable.org/usermanual/development/en/overview/workflow/import-review/):
  adicionar à biblioteca registra imagens no banco sem precisar copiar ou mover os originais.

São referências de comportamento; não se pretende reproduzir suas políticas de escrita de
metadata/sidecars, que diferem das garantias deste produto.

## Opções

| Opção | Benefício | Custo e limite |
| --- | --- | --- |
| Navegador puro de pastas | Abrir uma pasta e ver imagens imediatamente | Busca/calendário globais exigem varrer tudo ou introduzir índice; persistência de favoritos ainda requer armazenamento |
| Biblioteca interna gerenciada + indexador | UX simples e reuso do catálogo e dos casos Python existentes | Exige backup das anotações, autorização persistente de raízes e tratamento de mudanças/offline |
| Catálogos manuais como fluxo principal | Controle explícito e portabilidade do arquivo | Fricção atual; inadequado como experiência padrão para este público |

Recomendação: biblioteca interna gerenciada como padrão; catálogos externos ficam em opções
avançadas. A primeira versão acompanha pastas enquanto o app estiver aberto e reconcilia ao
iniciar, sem exigir um serviço residente do sistema. Não substituir Python/SQLite, criar daemon do sistema ou adicionar infraestrutura.

## Fluxo recomendado

1. O app abre sua biblioteca principal automaticamente. Para uma instalação nova, cria o banco
   em diretório privado e persistente de dados da aplicação, fora do acervo.
2. O usuário escolhe Adicionar pasta e autoriza acompanhar aquela pasta e suas subpastas uma vez.
3. O app descobre imagens, extrai metadata e prepara miniaturas em segundo plano. Progresso e
   problemas ficam em Notificações; o usuário pode navegar durante o trabalho.
4. Mudanças posteriores disparam verificações incrementais das raízes autorizadas. Eventos de
   filesystem são indícios para uma nova observação, nunca provas de identidade ou exclusão.
5. O usuário pode pausar ou remover o acompanhamento. Isso não apaga os originais.

Não pedir seleção de cada foto nem uma proposta técnica por atualização normal. Pedir decisão
quando houver conflito de identidade, troca de dispositivo/raiz, escopo novo ou ação destrutiva.
O modo de revisão explícita atual continua útil como operação avançada e ferramenta diagnóstica.

## Contratos que precisam evoluir

- A escolha atual concede autorização efêmera, de uso único e limitada à sessão. Não renová-la
  automaticamente nem persistir esse token: um acompanhamento durável precisa de contrato próprio
  de consentimento/revogação e de vínculo da raiz, revisado com os contratos de segurança.
- O scanner/preparador atual limita a árvore a 2000 entradas e a aplicação a 100 candidatos.
  Um indexador real precisa de unidades de trabalho menores, cobertura honesta, fila limitada,
  cancelamento e retomada. Aumentar os limites ou executar o scanner completo a cada evento não
  resolve a arquitetura de grandes acervos.
- Pastas offline, discos removíveis, permissões perdidas e arquivos substituídos são estados
  distintos. Não concluir missing por indisponibilidade, nem unir Assets por hash/path/inode.
- Mudanças ambíguas e renomes exigem reconciliação conservadora, preservando UUIDs e anotações.
- O banco gerenciado precisa de backup/restauração. Catálogos existentes não devem ser copiados,
  mesclados, descartados ou substituídos automaticamente.
- Os laboratórios anteriores usavam userData temporário e removiam esse diretório ao sair. O fluxo normal agora usa perfil persistente; somente demonstração e smoke explícito continuam temporários. O catálogo
  principal nunca pode ser armazenado nesse diretório efêmero. O lifecycle persistente deve ser
  explícito e verificado antes de oferecer uma biblioteca interna como padrão.

## Sequência de implementação proposta

1. Biblioteca principal gerenciada: bootstrap privado/persistente, reabertura automática, backup,
   compatibilidade com o catálogo já existente e gestão manual em opções avançadas.
2. Acompanhamento autorizado de pastas: consentimento persistente/revogação e primeira indexação
   incremental com progresso, sem tocar nos originais.
3. Monitoramento incremental: debounce, reconciliação ao iniciar/reconectar, quotas, pausa e
   recuperação de eventos perdidos. Validar grandes árvores sintéticas e mídias offline.

Aceite de UX: abrir o app → adicionar pasta → visualizar imagens; reiniciar mantém favoritos e
anotações; acrescentar uma imagem à pasta acompanhada a torna visível sem selecionar catálogo
ou repetir autorizações de rotina. Nenhuma promessa de monitoramento funcional nesta avaliação.
