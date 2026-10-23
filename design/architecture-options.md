# Opções arquiteturais

## Recomendação: monólito local modular

Um único processo Python 3.13+, empacotado futuramente como aplicação desktop, com limites internos claros e SQLite. A interface gráfica deve depender de casos de uso, não acessar banco ou filesystem diretamente.

```text
UI/CLI (futura)
      │
Application use cases
      │
Domain ── ports ── adapters
                   ├─ SQLite catalog
                   ├─ filesystem/import
                   ├─ metadata extractors
                   ├─ thumbnail cache
                   └─ duplicate provider (futuro)
```

Módulos candidatos: `domain`, `application`, `catalog`, `filesystem`, `metadata`, `importing`, `thumbnails` e `audit`. O domínio não importa SQLite, Pillow, GUI ou Duplicate Lab. Operações longas podem usar fila local persistida, sem broker externo.

**Por quê:** menor custo operacional, transações locais, backup simples, boa testabilidade e fronteiras suficientes para substituir extratores ou UI.

## Alternativa A: núcleo + worker local separado

Processo principal e worker local para metadados/thumbnails, comunicando por fila SQLite ou IPC. Isola falhas de codecs e mantém UI responsiva, mas adiciona lifecycle, recuperação e empacotamento. Adotar somente quando medições mostrarem necessidade; contratos de jobs já podem ser desenhados para permitir essa evolução.

## Alternativa B: serviço HTTP local

Backend local com API e UI separada. Facilita múltiplos clientes, mas cria autenticação local, portas, CORS, lifecycle e versionamento prematuros. Não recomendada para a primeira versão. A separação por portas no código fornece testabilidade sem rede.

## Importação segura

Pipeline recomendado: `discover -> inspect -> plan -> user confirmation -> copy -> fsync/verify -> catalog -> report`. Conflitos nunca sobrescrevem silenciosamente. Move é composição posterior de cópia verificada + confirmação + remoção auditada. Uma sessão interrompida retoma por itens idempotentes.

## Metadados

Leitura inicial é read-only. Escrita futura deve gerar plano e backup/sidecar conforme política. Preferir padrões interoperáveis quando confirmados, preservar bytes desconhecidos e jamais gravar GPS ou correções silenciosamente. O catálogo registra anotações próprias independentemente do arquivo.

## Fronteira com o Duplicate Lab

Não importar seus módulos nem schema. Definir um port versionado e pequeno, implementável no futuro por subprocesso/CLI ou adaptador:

```text
DuplicateProvider
  exact_groups(asset_refs) -> ExactGroup[]
  similar_candidates(asset_ref, policy) -> Candidate[]
  preferred_variant(group, policy) -> Recommendation
```

Entradas usam referências estáveis e fatos mínimos (hash, dimensões, codec), nunca caminhos internos do Lab como contrato. Saídas são evidências e recomendações, não mutações. Toda substituição/remoção permanece caso de uso do Photo Manager com revisão humana e auditoria. ORB experimental não é incorporado.

## Incrementos pequenos

1. ADRs para identidade de Asset, política de datas e escrita de metadados.
2. Protótipo descartável de schema + migrações usando arquivos sintéticos, não acervo pessoal.
3. Scanner read-only com manifesto JSON e testes de EXIF ausente/divergente.
4. Planejador de importação dry-run com colisões e retomada simulada.
5. Catálogo mínimo e reconciliação de movimento por evidência forte.
6. Somente então contratos de UI e thumbnails; integração de duplicatas depois.

