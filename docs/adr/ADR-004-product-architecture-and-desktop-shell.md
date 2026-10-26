# ADR-004 — Arquitetura do produto e shell desktop

- Status: Aceito
- Data: 2026-10-24

## 1. Contexto

As Foundations estabeleceram um catálogo SQLite e casos de uso Python locais, mas ainda não
formalizaram a composição do produto, a tecnologia da interface nem a fronteira de distribuição.
Os laboratórios existentes também precisam alimentar o produto sem se tornarem dependências de
runtime ou autoridades sobre seu domínio.

## 2. Decisão

O PlayMemories Photo Manager é um produto único, local-first e organizado como monólito modular.
O backend e os casos de uso permanecem em Python; o catálogo local permanece em SQLite. A
interface será desenvolvida em React com TypeScript e dependerá dos casos de uso do produto, sem
acessar diretamente SQLite ou o filesystem.

Electron é o candidato preferencial para o shell desktop e a distribuição, condicionado à prova
de conceito definida em [Convergência do produto](../product-architecture-convergence.md). Esta
ADR não homologa Electron nem autoriza sua instalação. A PoC deverá validar segurança, lifecycle,
desempenho, operação offline e empacotamento antes de uma decisão definitiva.
Tauri permanece como alternativa técnica a avaliar se Electron não atender aos critérios, sem
decisão antecipada de migração ou introdução de Rust nesta etapa.

As responsabilidades ficam separadas:

- **interface:** apresentação, interação e estado visual em React + TypeScript;
- **backend:** domínio, casos de uso, políticas de segurança, catálogo e operações locais em
  Python;
- **shell e empacotamento:** janela, bootstrap, lifecycle, ponte com o backend e distribuição;
  Electron só ocupará essa função se for homologado.

As dependências apontam da interface e do shell para contratos estreitos dos casos de uso. O
backend não depende de React, Electron ou Tauri; o domínio não depende do catálogo SQLite, do
filesystem, da interface ou dos laboratórios. Adapters implementam as fronteiras definidas pelas
camadas internas, evitando dependências circulares.

Nenhum serviço externo é obrigatório para iniciar, operar ou preservar o catálogo. SaaS,
multitenancy e arquitetura cloud estão fora do escopo atual. Uma fronteira local de comunicação
necessária ao shell não transforma o backend em serviço remoto nem autoriza exposição em rede.

Sony Lab e Duplicate Lab permanecem independentes do runtime. O Sony Lab é fonte de requisitos e
referências de UX, não implementação nem autoridade normativa. Funcionalidades homologadas do
Duplicate Lab poderão ser reimplementadas ou incorporadas seletivamente como módulos internos,
sob os contratos, identidade e políticas do Photo Manager; seus módulos, schema e dependências
não são importados por padrão.

Esta decisão preserva integralmente:

- ADR-001: identidade lógica, evidências e reconciliação conservadora;
- ADR-002: proveniência e semântica temporal;
- ADR-003: organização e separação entre anotações e metadata.

## 3. Consequências

O produto pode evoluir e ser testado como módulos locais sem infraestrutura operacional externa.
A separação entre interface, backend e shell permite substituir o empacotador sem reescrever o
domínio. Em contrapartida, a distribuição deverá coordenar com segurança dois runtimes, tratar
processos órfãos e entregar o backend Python sem exigir instalação separada quando a solução de
empacotamento escolhida suportar isso.

O backend não deverá assumir Electron, e o frontend não deverá contornar seus casos de uso.
Workers, serviço HTTP local ou outros processos só serão introduzidos mediante necessidade
demonstrada e decisão específica; a PoC pode experimentar uma comunicação local mínima sem
promovê-la automaticamente à arquitetura definitiva.

## 4. Critérios de revisão

A escolha do shell será revisada após a PoC. Electron só poderá ser homologado se atender aos
critérios de segurança, lifecycle, galeria, thumbnails, desempenho, offline e distribuição
multiplataforma documentados. Falha material pode levar à avaliação de outro shell sem invalidar
o backend Python, o frontend React + TypeScript ou o monólito modular. Linux, Windows e macOS são
plataformas-alvo de compatibilidade; a ordem e a profundidade das avaliações não constituem
suporte homologado antes dos respectivos testes e artefatos de distribuição.
