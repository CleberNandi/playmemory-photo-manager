# PlayMemories Photo Manager

Projeto independente de discovery para um gerenciador local de fotografias e, futuramente, vídeos. O nome é provisório.

## Escopo dos Discoveries 01 e 02

- estudar, por evidência pública e análise estática segura, como o Sony PlayMemories Home importa, cataloga, apresenta e pesquisa mídia;
- avaliar catálogo, timeline, etiquetas, classificação, álbuns, metadados, miniaturas e movimentações externas;
- revisar o `photoOrganizer` e delimitar uma fronteira futura com o Duplicate Lab;
- propor modelo de domínio e opções arquiteturais pequenas, sem implementar produto, banco de produção ou interface gráfica.

## Princípios

Os originais permanecem a fonte de verdade do conteúdo. Catálogo, álbuns virtuais e etiquetas não alteram nem duplicam originais. Escritas em metadados serão explícitas, auditáveis e opt-in; GPS será tratado como dado sensível. Operações destrutivas e decisões de duplicidade exigirão revisão humana.

## Foundation 01

A arquitetura-base é um monólito local modular em Python com SQLite. A Foundation 01 encerra as decisões sobre identidade, tempo e anotações sem implementar banco, scanner ou interface:

- [ADR-001 — Identidade de Asset](docs/adr/ADR-001-asset-identity.md)
- [ADR-002 — Datas e proveniência temporal](docs/adr/ADR-002-temporal-provenance.md)
- [ADR-003 — Organização, anotações e metadados](docs/adr/ADR-003-annotations-and-metadata.md)

## Estado dos Discoveries

O instalador `PMHOME_5501DL` não estava disponível durante o Discovery 01. Ele foi localizado posteriormente e analisado estaticamente no Discovery 02, sem execução ou Wine. A amostra é um instalador de rede parcial, não contém o payload principal e permanece isolada fora do controle de versão. Cada conclusão distingue documentação oficial, evidência do pacote, hipótese arquitetural e funcionalidade não confirmada.

## Documentos

- [Análise do instalador](research/sony-installer-analysis.md)
- [Funcionalidades do PlayMemories Home](research/playmemories-features.md)
- [REA e ferramentas](research/rea-analysis.md)
- [Revisão do photoOrganizer](research/photoorganizer-review.md)
- [Modelo de domínio](design/domain-model.md)
- [Opções arquiteturais](design/architecture-options.md)
- [Relatório consolidado](reports/discovery-01.md)
- [Relatório do instalador Sony](reports/discovery-02-sony-installer.md)

