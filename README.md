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

## Foundation 02

A primeira camada persistente está implementada com Python 3.13+, `sqlite3` e SQLite
`STRICT`. Ela contém o catálogo mínimo de Assets, localizações, álbuns, tags, metadata,
anotações e referências para thumbnails. Não lê nem altera fotografias: todos os testes usam
bancos e dados sintéticos temporários.

O desenho físico, as garantias e as limitações estão em
[Arquitetura da persistência](docs/persistence.md). As migrações SQL ficam em
`src/playmemories_photo_manager/catalog/migrations` e são aplicadas exclusivamente por
`initialize_database()`; essa entrada habilita e verifica foreign keys e registra as funções
Unicode exigidas pelas constraints.

### Ambiente e validação

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Inicialização programática de um catálogo novo ou existente:

```python
from playmemories_photo_manager.catalog import initialize_database

connection = initialize_database("catalog.sqlite3")
connection.close()
```

Arquivos `*.db`, `*.sqlite` e `*.sqlite3` permanecem ignorados. Catálogos reais devem ficar
fora do repositório e receber backup consistente pela API SQLite.

## Foundation 03

A camada de aplicação oferece contratos Python tipados e casos de uso transacionais para Assets,
raízes, localizações, álbuns, tags e anotações. Ela reutiliza a conexão gerenciada da Foundation
02, mantém SQL nos repositórios e não acessa mídia ou filesystem.

```python
from playmemories_photo_manager.catalog import Catalog, initialize_database

connection = initialize_database("catalog.sqlite3")
catalog = Catalog(connection)
asset = catalog.create_asset("photo")
album = catalog.create_album("Selecionadas")
catalog.add_asset_to_album(album.id, asset.id)
connection.close()
```

Os contratos, erros, paginação, transações e a semântica de disponibilidade estão documentados
em [Camada de aplicação do catálogo](docs/catalog-application.md).

## Foundation 04A

O scanner read-only enumera uma raiz explicitamente fornecida e produz observações estruturadas,
falhas e status de completude. Ele não segue links, não lê conteúdo, não calcula hashes e não
altera o catálogo ou a árvore observada. Os contratos e limites de portabilidade/TOCTOU estão em
[Scanner read-only](docs/readonly-scanner.md).

## Foundation 04B.1

O avaliador puro valida a coerência estrutural de um `ScanResult`, classifica cobertura e separa
observações diretas, inferências inconclusivas, limitações de portabilidade e impedimentos para
decisões futuras. Ele não acessa filesystem ou SQLite e não altera o catálogo. Os contratos estão
em [Avaliação de evidências do filesystem](docs/evidence-evaluation.md).

## Foundation 04B.2

O Change Planner puro compara evidências avaliadas com um snapshot lógico e limitado de uma raiz
do catálogo. Ele distingue localização conhecida observada, candidato de arquivo novo, resultado
inconclusivo e bloqueio, sem consultar SQLite ou filesystem e sem autorizar `missing`, importação,
merge ou qualquer mutação. O contrato e as regras conservadoras estão em
[Planejamento de mudanças do catálogo](docs/catalog-change-planning.md).

## Foundation 04C.1

O primeiro fluxo vertical executa scanner, avaliação e planejamento antes de aceitar uma seleção
explícita de candidatos. O lote autorizado cria Assets e FileLocations em uma única transação,
revalida raiz e caminhos, evita duplicidade em reexecuções e nunca infere `missing`, hash ou merge.
Contratos, autorização, conflitos, proveniência e limites de TOCTOU estão em
[Catalogação controlada](docs/catalog-ingestion.md).

## Direção do produto desktop

O produto converge para uma aplicação local-first única: monólito modular com backend Python,
catálogo SQLite e frontend React + TypeScript. Electron é o candidato preferencial para shell e
distribuição, mas depende de uma prova de conceito e ainda não está homologado; Tauri permanece
como alternativa técnica. A decisão e os critérios estão em
[ADR-004](docs/adr/ADR-004-product-architecture-and-desktop-shell.md) e no [documento de
convergência](docs/product-architecture-convergence.md).

## MVP Preview 02

A API Python read-only da galeria oferece paginação keyset, detalhes de Asset com proveniência e
um store POSIX confinado para thumbnails sintéticas pregeradas. Não há HTTP, decoder, frontend ou
leitura de originais. Contratos, exemplos, plano SQLite e limites de segurança estão em
[Gallery read model](docs/gallery-read-model.md).

## Duplicate Integration 01A

A API Python interna de duplicatas exatas pré-agrupa FileLocations por tamanho e confirma
igualdade binária com SHA-256 sob leitura POSIX confinada. Assets e todas as localizações são
preservados; hardlinks, cobertura incompleta e alterações observáveis permanecem explícitos. Não
há persistência de decisões nem mutação de mídia. O contrato está em
[Detecção read-only de duplicatas exatas](docs/exact-duplicates.md).

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
