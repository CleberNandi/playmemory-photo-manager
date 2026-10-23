# Análise estática do instalador Sony

## Histórico e escopo

No Discovery 01, em 2026-10-23, o instalador não foi localizado na busca então realizada. Depois dessa investigação, o operador informou sua localização exata e o Discovery 02 encontrou `/home/arch-nandi/Workspace/personal/PMHOME_5501DL.zip`. O achado posterior não altera nem apaga a conclusão histórica do Discovery 01.

Nenhum binário foi executado e Wine não foi usado. O ZIP original permaneceu no local informado; somente seu conteúdo foi extraído para `research/artifacts/sony-pmhome/`, área ignorada pelo Git.

## Identificação

| Item | Resultado |
|---|---|
| Nome | `PMHOME_5501DL.zip` |
| Caminho original | `/home/arch-nandi/Workspace/personal/PMHOME_5501DL.zip` |
| Tamanho | 16.350.400 bytes |
| SHA-256 | `5fbbbf1ad1ffc243177143cfaf91e593f2a04d48385cd9e87a846bb21989ce9c` |
| Tipo | ZIP deflate, mínimo ZIP 2.0 |
| Conteúdo | `PMHOME_5501DL/PMHOME_5501DL.exe`, 16.410.600 bytes |
| SHA-256 do EXE | `0667ff12170cad0009f35d54ab278cc4eadd83f7b598a3df507a40f13e4e6349` |
| EXE | PE32 GUI, Intel i386/x86, subsistema Windows 6.0, 5 seções |
| Produto/versão | PlayMemories Home; `ProductVersion 10.5.01.05091`; `FileVersion 1.0.00` |
| Empacotador | Microsoft Cabinet Self-Extractor/IExpress (`WEXTRACT.EXE`) |

O PE tem `DYNAMIC_BASE`, `NX_COMPAT`, Control Flow Guard e tabela de certificados Authenticode. O certificado incorporado identifica `Sony Imaging Products & Solutions Inc.`, emitido por `Symantec Class 3 SHA256 Code Signing CA`, válido de 2018-02-16 a 2019-02-16. A cadeia foi lida estaticamente com OpenSSL; a validade criptográfica do Authenticode e o timestamp não foram verificados porque `osslsigncode`/`pesign` não estão instalados. Confirma-se a presença e identidade declarada, não “assinatura válida”.

## Estrutura extraída

O autoextrator contém 11 arquivos:

- `Bootstrap.exe` (8.151.016 bytes), orquestrador/downloader;
- três MSI auxiliares: `PMB_ModeEditor_PMH.msi`, `PMB_ModeEditor_ACMC.msi` e `PMB_ServiceUploader.msi`;
- `EnvironmentCheckTool.exe`;
- `setup.ini`, `version.txt` (`10.5.01.05091`) e `fileMD5List.csv`;
- `EULA.zip`, com EULAs e políticas de privacidade localizadas;
- scripts de reparo `PMH_Repair_EN.bat` e `PMH_Repair_JP.bat`.

Os MSI são bases Windows Installer x86 criadas com WiX 3.0 em 2018-05-09. Não puderam ser abertos pelo libarchive disponível, e nenhuma ferramenta MSI adicional foi instalada.

Este artefato é um instalador de rede, não o pacote completo. `Bootstrap.exe` referencia módulos a baixar (`PMB.msi`, `SOHLib.zip`, DirectX e outros); `setup.ini` estima 500 MiB de arquivos do produto. O manifesto `fileMD5List.csv` lista 751 caminhos esperados (42 EXE, 679 DLL e 30 filtros AX) e hashes MD5, mas esses binários não estão no ZIP. Seus nomes evidenciam a composição planejada, não comportamento em execução.

## Componentes e tecnologias observados

Presentes: PE32 nativo, IExpress/Cabinet, Windows Installer/WiX, INI, ZIP, RTF, batch e CSV/MD5. Os imports do autoextrator incluem Cabinet API, registro, recursos, filesystem e criação de processos, coerentes com wrapper de instalação.

Referenciados no manifesto: `PMBBrowser.exe`, `PMBContentAnalyzer.exe`, `PMBDeviceInfoProvider.exe`, `PMBVolumeWatcher.exe`, `PMBSettingsTool.exe`, `PMBMediaExporter.exe`, `PMBWifiImportSetting.exe`, `PMBMPThumb.exe`, `XMPCore.dll`, `XMPFiles.dll`, filtros de mídia e DLLs de localização. Há componentes x86 e x64 de conversão. Isso sustenta uma aplicação Windows nativa modular e localizada, mas os arquivos principais não puderam ser examinados.

## Evidência funcional

### Catálogo, álbuns, etiquetas e avaliações

Os scripts de reparo confirmam áreas persistentes `Sony Corporation\PMB`, chaves de registro PMB e dados por usuário. O manifesto confirma browser e analisador de conteúdo. Porém não há banco de catálogo, schema nem componente principal; não foi encontrada evidência de SQLite. Álbuns, labels, ratings e suas relações permanecem sem confirmação pelo pacote. A documentação oficial do Discovery 01 continua sendo a evidência para labels e ratings.

### Cache e miniaturas

O script de reparo nomeia `%TMP%\PMBThumbnailCache`, `TempPMBThumbnailCache`, `.Sony_PMBrowser3000_BrowserDiskCache` e seu índice. O manifesto referencia `PMBMPThumb.exe`. Isso confirma caches separados de miniaturas e de disco no produto instalado. Formato, chave, dimensões, invalidação e lifecycle não são demonstrados.

### Metadados e sidecars

O manifesto referencia `XMPCore.dll` e `XMPFiles.dll`, evidência forte de que componentes Adobe XMP integram a distribuição planejada. Isso confirma tecnologia XMP no produto, mas não quais campos ou arquivos são lidos/escritos, nem interoperabilidade de labels/ratings. Não foram localizadas referências conclusivas a IPTC, EXIF, MODD, MOFF ou THM no conteúdo presente; o suporte documentado a EXIF e sidecars Sony permanece evidência documental.

### Importação e organização temporal

`PMBVolumeWatcher.exe`, `PMBDeviceInfoProvider.exe`, `PMBWifiImportSetting.exe`, `SMImport.ax`, `PMBContentAnalyzer.exe` e a área `%APPDATA%\Sony Corporation\Importer` constituem evidência de componentes dedicados à descoberta/importação de mídia e câmeras, inclusive Wi-Fi. Nomes isolados não provam regras de deduplicação, destino, retomada ou organização por data. O pacote não contém configuração ou schema que esclareça precedência temporal.

## Limitações e hipóteses

Não houve download dos módulos remotos, análise dinâmica, instalação, Wine ou decompilação. O manifesto descreve alvos ausentes e pode incluir componentes opcionais. Strings e nomes foram usados para localizar perguntas, nunca como prova definitiva de comportamento. Sem o `PMB.msi`/payload principal ou uma instalação legítima existente, catálogo, schemas, UI principal e algoritmos permanecem opacos.

Ghidra não se justifica para o wrapper IExpress: as perguntas relevantes estão nos módulos principais ausentes. Caso esses módulos sejam obtidos legitimamente, candidatos precisos seriam `PMBBrowser.exe`, `PMBContentAnalyzer.exe`, `PMBMPThumb.exe`, `XMPCore.dll`/`XMPFiles.dll` e DLLs de persistência que o novo inventário revelar.
