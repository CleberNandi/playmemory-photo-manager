# ADR-002 — Datas e proveniência temporal

- Status: Aceito
- Data: 2026-10-23

## 1. Contexto

Fotografias e vídeos podem fornecer datas em EXIF, XMP, sidecars, containers e filesystem, com precisão e timezone variados. Importação e correção manual acrescentam outros valores. Os Discoveries confirmam organização temporal no produto Sony, mas não sua precedência interna.

## 2. Problema

O catálogo precisa escolher uma data útil para ordenação sem apagar valores originais, inventar timezone ou tornar fontes conflitantes indistinguíveis.

## 3. Alternativas consideradas

1. **Um timestamp UTC obrigatório.** Facilita consultas, mas corrompe semanticamente valores locais sem offset conhecido.
2. **Primeiro valor encontrado.** É simples, porém instável entre extratores e não explica conflitos.
3. **Somente strings brutas.** Preserva dados, mas dificulta busca e calendário.
4. **Observações preservadas + projeção selecionada por política.** Mantém proveniência e oferece consultas previsíveis. É a escolhida.

## 4. Decisão

Cada valor temporal observado é preservado em `Metadata` com valor bruto, valor local parseado quando válido, fonte, chave de origem, precisão, offset/timezone quando explícito, versão do extrator e instante de extração. Um valor sem offset permanece “tempo local/flutuante”; não é convertido para UTC por suposição.

`Asset` mantém uma projeção de captura selecionada para consulta: valor local, offset opcional, precisão, `metadata_id` de origem e motivo/política da seleção. Essa projeção é derivada e pode ser recalculada sem destruir observações.

Precedência inicial para fotografias:

1. correção manual ativa do catálogo;
2. EXIF `DateTimeOriginal` válido, usando offset EXIF somente quando explicitamente presente e compatível;
3. data de captura XMP/sidecar explicitamente associada ao arquivo;
4. data de criação/captura do container de mídia;
5. EXIF `DateTimeDigitized`;
6. mtime do filesystem, marcado como fallback fraco;
7. sem data de captura.

Para vídeo, a data do container será candidata quando um extrator futuro documentar a semântica do campo. Até lá, não se generaliza a precedência de fotografia. Data de importação é sempre registrada na `ImportSession`; nunca substitui data de captura e pode ser usada apenas como eixo “adicionado em”.

Precisão é explícita (`second`, `minute`, `day`, `month`, `year` ou `unknown`). Componentes ausentes não são preenchidos artificialmente para elevar precisão. Timezone é representado como offset conhecido, zona nomeada conhecida ou desconhecido; offset não prova uma zona geográfica.

Conflitos são preservados. A projeção segue a precedência determinística, registra a escolha e sinaliza conflito relevante para revisão; não reescreve a fonte perdedora. Correção manual cria uma anotação temporal do catálogo com valor, timezone/offset opcional, precisão, justificativa e timestamps de criação/alteração. Ela não altera EXIF, XMP, sidecar ou arquivo original.

## 5. Justificativa

Separar observações da projeção evita perda de dados e torna o calendário testável. Datas sem timezone permanecem honestas. A precedência inicial privilegia intenção de captura e correção explícita, enquanto mtime é apenas fallback porque cópias e restaurações o alteram.

## 6. Invariantes

- Todo valor temporal selecionado aponta para sua fonte ou correção manual.
- O valor bruto extraído é preservado.
- Timestamp sem timezone não é convertido para UTC.
- Precisão não é inferida além do conteúdo disponível.
- `imported_at` nunca é `captured_at`.
- Correção manual não modifica nem elimina metadata extraída.
- Conflitos permanecem consultáveis após a seleção.
- Reextração pode substituir a projeção derivada, mas não uma correção manual ativa.

## 7. Consequências

Consultas temporais precisam lidar com valores flutuantes e instantes absolutos. Ordenação entre ambos deve ser definida na camada de aplicação e indicar incerteza. O modelo guarda mais contexto que um timestamp único, mas evita migrações destrutivas quando vídeo e sidecars forem adicionados. A UI futura precisará distinguir “capturada”, “modificada” e “importada”.

## 8. Casos de teste futuros

- EXIF com offset seleciona instante e preserva bruto;
- EXIF sem offset permanece local/flutuante;
- DST ou timezone geográfico não é deduzido por coordenada ou máquina;
- XMP conflitante é preservado e sinalizado sem superar EXIF pela política inicial;
- mtime só vence quando fontes de captura válidas faltam;
- importação sem metadata resulta em fallback fraco ou sem data, nunca na data de importação;
- precisão de apenas dia não ganha hora `00:00:00` como fato;
- correção manual vence a projeção e pode ser removida para revelar a seleção automática;
- EXIF inválido permanece como valor bruto com erro de parse;
- reextração com nova versão não apaga observações históricas necessárias à auditoria.

## 9. Questões adiadas

- campos e precedência específicos por container de vídeo;
- associação e resolução de múltiplos sidecars;
- comparação/ordenação global entre tempos flutuantes e absolutos;
- tolerância para conflitos de poucos segundos;
- UX de correções em lote e deslocamento de relógio;
- eventual exportação temporal para XMP/sidecar.
