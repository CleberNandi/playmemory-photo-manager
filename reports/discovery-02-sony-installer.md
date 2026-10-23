# Discovery 02 — instalador Sony PMHOME_5501DL

Data: 2026-10-23

## Resumo executivo

O instalador original foi localizado e preservado. Trata-se de `PMHOME_5501DL.zip`, SHA-256 `5fbbbf1ad1ffc243177143cfaf91e593f2a04d48385cd9e87a846bb21989ce9c`, contendo um autoextrator IExpress PE32 x86 do PlayMemories Home 10.5.01.05091. A análise foi exclusivamente estática.

O principal resultado é que esta distribuição é um instalador de rede, não o produto completo. Ela traz bootstrap, três MSI auxiliares, EULAs, configuração, manifesto e scripts de reparo; os binários centrais seriam baixados. Assim, o pacote acrescenta evidências úteis sobre componentes, XMP, importação e caches, mas não contém catálogo/schema ou implementação suficiente para confirmar álbuns, persistência de labels/ratings ou regras temporais.

## 1. Inventário do instalador

| Campo | Valor |
|---|---|
| Original | `/home/arch-nandi/Workspace/personal/PMHOME_5501DL.zip` |
| Tamanho | 16.350.400 bytes |
| SHA-256 | `5fbbbf1ad1ffc243177143cfaf91e593f2a04d48385cd9e87a846bb21989ce9c` |
| ZIP interno | `PMHOME_5501DL/PMHOME_5501DL.exe`, 16.410.600 bytes |
| SHA-256 do EXE | `0667ff12170cad0009f35d54ab278cc4eadd83f7b598a3df507a40f13e4e6349` |
| Tipo/arquitetura | Microsoft IExpress/Cabinet Self-Extractor; PE32 GUI Intel x86 |
| Produto/versão | PlayMemories Home 10.5.01.05091; launcher FileVersion 1.0.00 |
| Assinatura | Authenticode presente; certificado Sony Imaging Products & Solutions Inc., Symantec, 2018–2019; integridade criptográfica não validada |

O SHA-256 do ZIP foi recalculado após a análise e permaneceu idêntico. O arquivo original não foi copiado, alterado ou executado.

## 2. Componentes identificados

Arquivos realmente extraídos: `Bootstrap.exe`, `EnvironmentCheckTool.exe`, três MSI (`PMB_ModeEditor_PMH`, `PMB_ModeEditor_ACMC`, `PMB_ServiceUploader`), `setup.ini`, `version.txt`, `fileMD5List.csv`, `EULA.zip` e dois scripts de reparo. Os MSI x86 foram criados com WiX 3.0.

O manifesto descreve 751 arquivos do payload ausente: 42 EXE, 679 DLL e 30 AX. Entre eles estão browser, content analyzer, volume watcher, device provider, settings, media exporter, importação Wi-Fi, gerador de thumbnails, XMP e filtros/engines de mídia. Como são referências com MD5, não binários presentes, não foram tratados como prova de comportamento interno.

## 3. Tecnologias encontradas

- Presentes: PE32 nativo, IExpress/Cabinet, Windows Installer/WiX, ZIP, INI, RTF, batch, CSV/MD5, registro e recursos Win32.
- Referenciadas: XMP (`XMPCore.dll`, `XMPFiles.dll`), DirectShow/AX, componentes x86/x64 de mídia, localização em 18 idiomas e módulos de rede/serviço.
- Não encontrada: evidência de SQLite ou outro engine de banco no conteúdo presente.

## 4. Catálogo, álbuns, etiquetas e avaliações

Há evidência de diretórios persistentes PMB por máquina/usuário e de componentes Browser/ContentAnalyzer. Não há arquivo de catálogo, schema, tabela, SQL ou binário principal. Portanto:

- catálogo separado do original continua fortemente sustentado pela documentação Sony e pelos caminhos de dados, mas o formato segue desconhecido;
- labels e ratings continuam confirmados pela documentação, não pela implementação desta amostra;
- álbuns locais, relação muitos-para-muitos e smart albums permanecem não confirmados;
- nenhum nome/string isolado foi promovido a prova de semântica.

## 5. Cache, miniaturas e metadados

Os scripts de reparo confirmam `%TMP%\PMBThumbnailCache`, `TempPMBThumbnailCache`, `.Sony_PMBrowser3000_BrowserDiskCache` e `.idx`; o manifesto referencia `PMBMPThumb.exe`. A existência de cache dedicado está confirmada, mas não seu formato, chave ou invalidação.

`XMPCore.dll` e `XMPFiles.dll` confirmam tecnologia XMP na composição planejada. Não permitem afirmar se labels/ratings são gravados em XMP nem se há sidecar. Esta amostra não adicionou evidência conclusiva sobre IPTC, EXIF, MODD, MOFF ou THM além da documentação oficial já registrada.

## 6. Importação e organização temporal

O conjunto `PMBVolumeWatcher`, `PMBDeviceInfoProvider`, `PMBWifiImportSetting`, `SMImport` e `PMBContentAnalyzer`, junto da pasta por usuário `Importer`, confirma separação modular para descoberta/importação de câmera e mídia, inclusive Wi-Fi. Regras de duplicidade, retomada, integridade, ordenação por captura e precedência EXIF/container/filesystem não foram encontradas.

## 7. Relação com o modelo de domínio

Os achados reforçam, sem exigir compatibilidade binária:

- `Asset` separado de `FileLocation`, pois dados de gestão e caches são separados da mídia;
- `Thumbnail` regenerável com versão/estado próprio;
- `Metadata` com origem e proveniência, especialmente diante de XMP e sidecars;
- `ImportSession`/`ImportItem` auditáveis, dado o subsistema dedicado de importação;
- `AssetTag` e `AlbumAsset` como modelos próprios do novo produto, sem alegar equivalência ao schema Sony.

Não se deve copiar código, formatos proprietários ou nomes internos Sony. O novo modelo deve ser definido pelos requisitos e validado com mídia sintética.

## 8. REA e análise profunda

REA 6.7.0 do Reference Study foi confirmado e usado. `inspect-artifact` e `inspect-pe-resources` produziram evidência estática; o segundo contou 45 recursos e confirmou x86. `inspect-binary-layout` informou ausência do backend Python/pwntools requerido. Ghidra também não está configurado.

Não se recomenda instalar Ghidra para este wrapper. O benefício só surge com o payload principal legítimo e uma pergunta específica, por exemplo persistência no `PMBBrowser`, geração de cache no `PMBMPThumb` ou pipeline XMP. Nesse caso seriam necessários Ghidra 12.1.x, espaço/RAM/tempo definidos e projeto isolado no workspace.

## 9. Funcionalidades ainda não confirmadas

- schema/engine do catálogo e migrações;
- álbuns locais, smart albums e relação com labels;
- armazenamento e interoperabilidade de labels/ratings;
- leitura/escrita efetiva de EXIF, IPTC, XMP, MODD, MOFF e THM;
- formato, chave e invalidação das miniaturas;
- regras de duplicidade, retomada e integridade da importação;
- precedência e timezone na organização temporal;
- tecnologia e estrutura da UI principal.

## 10. Limitações da análise estática

O downloader não inclui o payload central e seus endpoints antigos podem já estar indisponíveis. Não houve download, execução, instalação, Wine, análise de tráfego, acesso a mídia pessoal nem engenharia reversa profunda. O Authenticode foi identificado e seus certificados lidos, mas não validado ponta a ponta. Os MSI auxiliares não foram extraídos por falta de parser disponível; não foi instalada dependência.

## 11. Recomendações objetivas

1. Iniciar a Foundation 01 com contratos e schema próprios: há evidência suficiente para scanner read-only, catálogo SQLite local, importação dry-run, metadata com origem e cache regenerável.
2. Manter álbuns/tags como requisitos do novo produto, não como clonagem do Sony.
3. Fechar antes da implementação os ADRs de identidade do asset, precedência temporal e política de escrita/sidecar.
4. Não bloquear a Foundation por Ghidra. Só retomar engenharia reversa se houver acesso legítimo ao payload instalado/completo e uma decisão arquitetural que não possa ser resolvida por testes próprios.
5. Se compatibilidade/migração de uma instalação Sony real virar requisito, coletar com autorização apenas amostras sintéticas e snapshots de catálogo/cache, preservando privacidade e proveniência.

## 12. Encerramento e conformidade

- instalador original inalterado, com hash final igual ao inicial;
- artefatos extraídos e temporários isolados sob `research/artifacts/sony-pmhome/` e ignorados pelo Git;
- documentação do Discovery 01 preservada e complementada por adendo histórico;
- Duplicate Lab e Reference Study não modificados;
- nenhum binário Sony incluído no Git;
- nenhum executável desconhecido, instalador ou Wine executado;
- nenhuma dependência instalada e nenhum remoto/push criado.

**Decisão:** existem evidências suficientes para iniciar a Foundation 01. Investigação adicional do produto Sony é opcional e só se justifica para compatibilidade/migração explícita, não para construir a fundação do Photo Manager.
