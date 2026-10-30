# Desktop MVP D04-02A — Preparação segura de catalogação

Data: 2026-10-30. **Planejamento proposto; implementação ainda não iniciada.**
Base remota confirmada: `main` em `337f8cd266bca19a591482a56aa41ad8a150a074`,
após integração fast-forward da PR #11, homologada pelo Gemini com PASS. O registro da PR
preserva os gates e as limitações manuais de D04-01B. Este documento não altera D04-00 ou ADRs.

## Objetivo e diagnóstico

Preparar uma proposta privada de catalogação de uma pasta explicitamente selecionada,
sem criar Assets ou FileLocations. D04-02B fará revisão humana, autorização e aplicação.
Referências normativas: [D04-00, §§6–8 e observação 02](desktop-mvp-d04-00.md),
[lifecycle proposto D03-02A](desktop-mvp-d03-02a.md) e ADR-001–004 em `docs/adr/`.

Inspeção confirma que o controlador/worker de D03-02A é contrato documental, não código
reutilizável existente. O scanner atual materializa entradas; `prepare_ingestion` usa snapshot
sem orçamento e a bridge despacha sequencialmente. Não habilitar essa chamada diretamente na UI.
O aplicador atual exige plano integralmente aplicável; filtrar a lista visual não resolve o
bloqueio de diretórios. Não relaxar `_require_applicable_plan` globalmente.

## Ordem de implementação e critérios de conclusão

1. **Coleta limitada e snapshot consistente.** Introduzir limites opcionais no scanner,
   preservando comportamento dos chamadores atuais. Contar entradas antes de acumular/ordenar,
   incluindo diretórios e excluídos; interromper no excesso, sem declarar cobertura completa.
   Consultar snapshot limitado dentro de uma leitura consistente, encerrada antes de ler mídia;
   preservar o digest lógico `read_version`, sem anunciá-lo como revisão transacional.
2. **Elegibilidade e recorte explícito.** Manter ScanResult, cobertura e diagnósticos originais.
   Produzir registro privado por candidato com ID opaco, classificação, motivo fixo, versão do
   perfil e evidências de abertura. Somente arquivo regular novo e JPEG aceito pode ser elegível.
   Diretórios cobertos e formatos excluídos recebem justificativa explícita; inconclusão de
   cobertura, conflito ou evidência física nunca pode ser descartada como simples exclusão.
   Definir contrato tipado do recorte e sua recomputação pelo aplicador antes de integrar a UI;
   não fabricar um plano READY por remoção de warnings ou edição do ScanResult.
3. **Worker e controlador Python.** Implementar o lifecycle de preparação específico com spawn
   de entry point fixo, sem shell e sem herdar SQLite ou descritores de mídia. Conexões abertas
   e fechadas pelo proprietário; canais/filas limitados, controle independente de progresso,
   um escritor de stdout. Uma operação por biblioteca; cancelamento cooperativo, terminação e
   reap obrigatório antes de liberar o slot. Nenhuma importação do detector de duplicatas.
4. **Seleção e grant.** Main abre diálogo de uma pasta e confirmação que explica recursividade,
   leitura e registro de configuração. Python valida raiz/ancestrais por descritores, identidade,
   sobreposição com raízes e destinos do catálogo. Só então registra/reutiliza LibraryRoot em
   comando curto. Grant privado vincula sessão, janela, identidade e escopo, vale cinco minutos
   para admissão e é consumido uma vez. Cancelar diálogo não registra nada; cancelar preparação
   pode deixar a raiz vazia. Troca/fechamento revogam grant e aguardam reap.
5. **IPC e UI.** Propor rotas próprias `ingestion.prepare/status/cancel/page`, sem paths ou MIME
   aceitos do renderer, mantendo validação de sender, sessão, geração e aridade de D04-01B.
   Publicar páginas só depois de validar resultado completo e reap. Progresso com fase/contagens
   reais e total null quando desconhecido. Preparação parcial/cancelada/limitada conserva apenas
   resumo limitado e não permite acessar proposta aplicável. Nenhuma rota de aplicação nesta fase.

## Orçamentos iniciais a medir antes da habilitação

| Recurso | Limite proposto / tratamento |
| --- | --- |
| Entradas observadas | 2.000; a entrada 2.001 encerra por resource_limit |
| Profundidade | 32; exceder bloqueia a proposta inteira |
| Proposta canônica privada | 8 MiB, incluindo evidências/diagnósticos; limitar durante construção |
| Snapshot catalogado | Até 2.000 localizações e 8 MiB; limite inclui consulta/materialização |
| Worker | 30 s, RSS 256 MiB; monitor Linux obrigatório, medir intervalo e overshoot |
| Página pública | Até 50 itens, dentro do envelope de resposta de 256 KiB da bridge |
| JPEG | Até 64 MiB, 40 milhões de pixels, 16.384 por eixo; sem decomprimir pixels |

Perfil JPEG ainda precisa especificar marcadores, comprimentos, dimensões, término, limites de
segmentos/bytes/tempo e corpus adversarial. SOI ou extensão isolados não bastam. A alternativa a
parser próprio é biblioteca com validação demonstrada, sujeita à decisão de dependência; este
plano não adiciona uma. Até revisão do perfil e corpus, classificação é unverified_format e o
fluxo real permanece desabilitado. Decodificação integral continua not_checked mesmo após aceite
estrutural. Não inferir EXIF, captura, hash, thumbnail ou preview.

## Evidência exigida e fora de escopo

Fixtures exclusivamente sintéticas: vazia, nested, links, raiz trocada, permission denied,
montagem fora de escopo, cancelamento, crash e worker resistente; 2.001 entradas, profundidade,
snapshot/proposta enormes, tempo/RSS e reap; JPEG truncado, assinatura enganosa, dimensões e
segmentos excessivos, leitura instável. Demonstrar zero INSERT Asset/FileLocation e ausência de
escrita em originais. Testar grants expirados/cruzados, respostas tardias e UI responsiva.
Medir custos e registrar limitações; sem monitor confiável, preparação indisponível nesse alvo.

Fora de escopo: apply, deduplicação, hash, merge de Assets, reconciliação completa, extração de
metadata, thumbnails, preview, migrações e suporte Windows não demonstrado. A observação de
reconexão de D04-01B permanece melhoria futura, sem refatoração oportunista neste incremento.

## Próxima revisão

Revisar a decomposição, o contrato de recorte (observação 02) e os critérios do perfil JPEG antes
de habilitar coleta real. Não se considera D04-02A implementado ou homologado por este plano.
O roteiro detalhado do perfil/corpus e as APIs exatas serão parte da implementação auditável;
nenhum resultado de teste de D04-01B comprova os novos orçamentos ou a preparação de mídia.

Validação desta entrega exclusivamente documental: uv sync --locked PASS; uv run pytest PASS
(359 testes); uv run ruff check . PASS; uv run ruff format --check . PASS; git diff --check
PASS e verificação no-index do arquivo novo sem mensagens de whitespace (status 1 esperado).
Build/smokes desktop não reexecutados: nenhum código desktop mudou. Gemini deste plano NOT RUN.
