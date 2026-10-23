# PlayMemories Home: mapa funcional e evidências

## Método e classificação

Este documento usa quatro classes: **D** (documentação oficial Sony), **P** (identificado no pacote), **O** (observação dinâmica autorizada) e **H** (hipótese). O Discovery 01 dispunha apenas de **D**; o Discovery 02 localizou o instalador de rede e acrescentou **P**. Não houve observação dinâmica. Inferências são marcadas **H**.

## Biblioteca e catálogo

| Achado | Classe | Confiança e limite |
|---|---:|---|
| Pastas de Pictures e Videos entram por padrão; outras pastas locais, de HDD externo e rede podem ser adicionadas. Mídia removível não pode ser pasta gerenciada. | D | Alta; [Adding / Removing folders](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/guide/windows/play/setting.html). |
| Importar ou instalar atualiza um “database”; acima de 10 mil mídias, muitos vídeos, rede ou HDD externo podem tornar a atualização lenta. | D | Alta; [database Q&A](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/qa/QA06.html). O motor e schema são desconhecidos. |
| Mudança/remoção externa de pasta não é automaticamente reconciliada: surge `X`; Update Database/Refresh remove referências antigas e a nova pasta precisa ser adicionada. | D | Alta; [missing thumbnail Q&A](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/qa/QA09.html). Renomeio por conteúdo/inode não foi demonstrado. |
| A pasta Documents/Sony PMB contém informação de gestão, incluindo labels e MapView; a mídia fica em suas próprias pastas e ambas precisam de backup. | D | Alta; [Data backup](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/guide/windows/backup/). Formato interno desconhecido. |
| Há miniaturas e ícones de estado/tipo. | D | Alta quanto à UI; [Main Window](https://support.d-imaging.sony.co.jp/support/app/playmemorieshome/en/help/win/main.html). Local/formato/invalidação do cache não confirmados. |
| O produto instalado mantém caches chamados `PMBThumbnailCache`, `TempPMBThumbnailCache` e `PMBrowser3000_BrowserDiskCache`; o manifesto referencia `PMBMPThumb.exe`. | P | Alta para existência/nome; formato e política de invalidação continuam desconhecidos. |

**H:** o aplicativo mantém um catálogo próprio que referencia arquivos externos, em vez de incorporar os originais. A combinação de “database”, pastas adicionadas, referências quebradas e backup separado sustenta a hipótese, mas pacote/schema não foram inspecionados.

## Organização, pesquisa e timeline

- **D:** modos Thumbnail, Details e Calendar; visualização por data de captura é documentada. Não foi confirmado agrupamento semântico em “eventos”.
- **D:** pesquisa por nome de arquivo, título, descrição, label, rating, tipo e câmera/lente. Fonte: [Searching images](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/guide/windows/play/search.html).
- **D:** propriedades mostram data, fabricante/modelo, velocidade, abertura, distância focal, ISO, white balance e flash; o usuário pode editar título, descrição, rating de 1–5 e labels personalizadas. Fonte: [Grouping images](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/guide/windows/play/grouping.html).
- **D:** data/hora pode ser corrigida individualmente ou em lote por deslocamento. Fonte: [Changing the date](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/guide/windows/edit/date.html). A documentação não diz se a escrita ocorre no arquivo, sidecar ou catálogo.
- **Não confirmado:** fallback para data de arquivo quando EXIF está ausente; resolução de divergência entre EXIF, sidecar e filesystem; timezone; calendário por dia/mês/ano em detalhe.

## Álbuns, etiquetas, favoritos e categorias

- **Confirmado (D):** labels personalizadas, títulos, descrições e ratings; busca/filtro por esses campos.
- **Confirmado (D):** a navegação “Favorites” corresponde a mídia marcada por rating no help legado; não há evidência de entidade Favorito independente.
- **Não confirmado:** álbuns locais/virtuais no PlayMemories Home, relação muitos-para-muitos de álbum e mídia, categorias distintas de labels e smart albums.
- **P:** o instalador de rede não contém o catálogo/schema principal e seu manifesto não fornece evidência suficiente sobre álbuns, labels ou ratings. O pacote não eleva esses itens além da evidência documental já registrada.
- **Separação importante:** a Sony documenta álbuns no serviço **PlayMemories Online**, que é outro produto e foi descontinuado; isso não prova álbuns locais no Home.

## Importação

- **D:** USB e cartões; seleção de todos os novos itens ou arquivos escolhidos; destino configurável. O padrão cria pastas por data de captura em Pictures. Fonte: [Import to external HDD](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/guide/windows/import/hdd.html) e [Handycam import](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/operation/import-cam.html).
- **D:** transferência Wi-Fi pode enviar somente itens novos; vídeos são desabilitados por padrão e XAVC S impede esse fluxo. Marcadores de vídeo não seguem por Wi-Fi. Fonte: [Wi-Fi import](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/operation/wifi-cam.html).
- **D:** configurações permitem opção de apagar na importação, mas a política e salvaguardas não estão descritas na página.
- **Não confirmado:** regra para nomes duplicados, hash/idempotência, preservação de timestamps, retomada transacional após interrupção e verificação byte a byte.

## Metadados e sidecars

- **D:** leitura de campos equivalentes a EXIF e informação GPS; suporte explícito de campos de câmera/captura.
- **D:** arquivos `.modd`, `.moff` e `.thm` são criados automaticamente e contêm informações necessárias como data de gravação ou GPS. Fonte: [sidecar Q&A](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/qa/QA05.html).
- **D:** `Sony PMB` contém informação de gestão, incluindo labels.
- **Não confirmado:** escrita/leitura XMP, IPTC, interoperabilidade das labels/ratings com outros gerenciadores, schema de MODD/MOFF, metadados proprietários específicos e se os campos editáveis alteram o original.
- **P:** `XMPCore.dll` e `XMPFiles.dll` constam no manifesto do produto, confirmando a inclusão planejada de tecnologia XMP. O sentido da operação, campos e arquivos afetados não são demonstrados. Não houve nova evidência binária conclusiva para IPTC, EXIF ou MODD/MOFF/THM.

## Componentes de importação identificados no pacote

- **P:** o manifesto lista `PMBVolumeWatcher.exe`, `PMBDeviceInfoProvider.exe`, `PMBWifiImportSetting.exe`, `SMImport.ax` e `PMBContentAnalyzer.exe`; o script de reparo referencia `%APPDATA%\Sony Corporation\Importer`.
- **Limite:** esses nomes confirmam componentes distribuídos/planejados para descoberta e importação, não regras de idempotência, colisão, retomada ou organização temporal.

## Fotografias e vídeos

**D:** formatos listados pela Sony: JPEG, MPO, TIFF, GIF, SRF/SR2/ARW; DV-AVI, Motion-JPEG, WMV, MPEG-1, MPEG-2, TS (AVC), MP4 (MPEG-4) e MP4 (AVI). Fonte: [Supported formats](https://www.sony.com/electronics/support/e-mount-body-ilce-7-series/ilce-7/articles/00070260). A lista pode variar por versão, codec, câmera e sistema.

Vídeos aparecem na mesma biblioteca, calendário, pesquisa e importação. A UI documenta miniaturas/ícones para 4K, high-speed, burst/markers e conteúdo editado. Há trim, combine, extração de frame e edição, com preservação dos originais em algumas operações; isso não demonstra o modelo interno de thumbnails. Fonte: [Editing videos](https://support.d-imaging.sony.co.jp/www/disoft/int/playmemories-home/en/guide/windows/edit/video.html).

## Limitações conhecidas da documentação

A documentação pública mistura help legado e guia atual, e funcionalidades variam por região, versão e dispositivo. O instalador 5.5.01 inspecionado é um downloader parcial: não contém os binários principais. Funções online/mapa foram descontinuadas; não devem orientar a arquitetura local. Nada aqui confirma engine/schema do banco, tecnologia da UI principal, algoritmo de thumbnails ou persistência de tags.

