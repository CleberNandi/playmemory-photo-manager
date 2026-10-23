# Discovery 01 — relatório consolidado

Data: 2026-10-23

## Resumo executivo

O Discovery confirma que o PlayMemories Home é orientado por catálogo: registra pastas, atualiza um banco na importação, oferece calendário, busca e anotações, e mantém informação de gestão separada dos originais. A documentação prova labels, rating, títulos, descrições, favoritos derivados de rating, sidecars e suporte conjunto a fotos/vídeos. Não prova álbuns locais, XMP/IPTC, schema do banco, tecnologia interna nem mecanismo do cache.

O instalador `PMHOME_5501DL` não foi localizado na busca segura e limitada. Consequentemente, não há achados do pacote, assinatura ou persistência interna. Nenhum executável foi baixado, iniciado ou extraído; Wine não foi usado.

> **Adendo histórico — Discovery 02:** após o encerramento desta investigação, o operador informou que `PMHOME_5501DL.zip` estava em `/home/arch-nandi/Workspace/personal/`. Ele foi localizado e analisado estaticamente no Discovery 02. As afirmações acima descrevem corretamente o estado do Discovery 01 e são preservadas; os novos achados estão em [discovery-02-sony-installer.md](discovery-02-sony-installer.md).

## 1. Instalador e componentes

Busca: `/home/arch-nandi` até quatro níveis e locais usuais Downloads/Download/Desktop/Documents até três níveis, incluindo o workspace. Resultado: ausente. Componentes Sony inspecionados: nenhum. O artefato exato e o procedimento futuro estão em [sony-installer-analysis.md](../research/sony-installer-analysis.md).

## 2. REA

REA 6.7.0 foi verificado com Node 24.22.1 isolado. CLI, diagnóstico e catálogo de capacidades funcionam; Ghidra, Hopper, IDA, JADX e Kuna não estão configurados. Recursos estáticos para inventário, PE, .NET, SQLite e `objdump` existem, mas decompilação nativa exige backend. Sem alvo, Ghidra seria custo sem pergunta concreta e não foi instalado. Consulte [rea-analysis.md](../research/rea-analysis.md).

## 3. Funcionalidades confirmadas

- biblioteca formada por pastas adicionadas e mídia importada, com banco atualizado;
- thumbnails e estados visuais; detalhes do cache não documentados;
- calendário, detalhes e miniaturas;
- busca por arquivo, título, descrição, labels, rating, tipo e câmera/lente;
- labels customizadas, rating 1–5, título e descrição; “Favorites” baseado em rating;
- importação USB/cartão/Wi-Fi, destino configurável e pasta por data de captura como padrão;
- leitura de dados de câmera/captura/GPS e sidecars MODD/MOFF/THM;
- fotos RAW/JPEG e diversos formatos de vídeo no mesmo navegador.

Mudanças externas não são reconhecidas como movimento: deixam `X` até atualização/refresh e adição da nova pasta. Isso justifica reconciliação explícita no novo produto.

## 4. Não confirmado

- álbuns locais/virtuais e relação muitos-para-muitos no PlayMemories Home;
- XMP/IPTC, interoperabilidade de tags/ratings e destino das edições de data;
- nomes/schema/tecnologia do banco, miniaturas e algoritmo de invalidação;
- política de nomes duplicados, integridade e retomada de importações;
- fallback e precedência entre datas EXIF, container, sidecar e filesystem;
- tecnologia dos executáveis 5.5.01.

Álbuns são requisito candidato do novo projeto, não funcionalidade atribuída ao Sony desktop. O serviço PlayMemories Online tinha álbuns, mas era produto separado.

## 5. Modelo e arquitetura

Modelo proposto: `Asset` separado de `FileLocation`; associações muitos-para-muitos `AlbumAsset` e `AssetTag`; `Metadata` com origem; `ImportSession`/itens auditáveis; `Thumbnail` regenerável; anotações do usuário separadas de metadata extraído. A proposta completa está em [domain-model.md](../design/domain-model.md).

Recomenda-se monólito local modular em Python 3.13+ com SQLite, filesystem como fonte do conteúdo e adapters para extração/cache. SQLite é proporcional para um usuário local, com foreign keys, índices, migrações, FTS5 e backups consistentes. Serviço HTTP/distribuído não se justifica. Veja [architecture-options.md](../design/architecture-options.md).

## 6. photoOrganizer

Disponível e revisado em modo read-only. Implementa apenas movimentação de JPEG por `DateTimeOriginal` e um script MD5 separado. Não tem testes funcionais ou licença identificada; o código não deve ser copiado. O conceito de política por data é aproveitável, mas exige planejamento, fallback, colisões, auditoria e operação não destrutiva. Veja [photoorganizer-review.md](../research/photoorganizer-review.md).

## 7. Fronteira com Duplicate Lab

O Lab permaneceu inalterado na branch observada `experiment/local-feature-matching`. A integração futura deve usar `DuplicateProvider` pequeno para grupos exatos, candidatos similares e recomendação de variante, retornando evidências sem mutação. Nenhum código ORB, schema interno ou dependência direta será incorporado; remoções/substituições ficam sob revisão humana no Photo Manager.

## 8. Recomendação e próximos passos

1. Obter do operador o caminho do instalador original apenas quando a análise do pacote for retomada; registrar hash e proveniência antes de copiar.
2. Fechar três ADRs: identidade lógica, precedência de data e política de escrita/sidecar.
3. Validar um schema descartável e migrações com mídia sintética.
4. Construir primeiro scanner read-only e planejador de importação dry-run.
5. Testar reconciliação conservadora de movimentos antes de GUI.
6. Adiar worker separado, vídeo profundo e Duplicate Lab até contratos e métricas exigirem.

## 9. Conformidade e limitações

- nenhum original, projeto vizinho, branch, dependência ou relatório existente foi modificado;
- nenhum instalador Windows, DLL ou binário PyInstaller foi executado;
- nenhuma dependência global ou ferramenta pesada foi instalada;
- não houve análise dinâmica;
- conclusões do pacote continuam pendentes da disponibilização do artefato.

## 10. Entregáveis

Foram criados `README.md`, `.gitignore`, três documentos de pesquisa obrigatórios, a revisão condicional do photoOrganizer, dois documentos de design e este relatório. O repositório Git foi inicializado localmente, sem remoto e sem commit.
