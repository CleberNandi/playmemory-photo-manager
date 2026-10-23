# REA: capacidade e limites

## Instalação verificada

Foi usada somente para diagnóstico a instalação isolada do Reference Study:

- pacote: `rea-agents` 6.7.0, licença MIT declarada;
- Node isolado: 24.22.1;
- CLI: `playmemories-reference-study/.tools/rea/node_modules/rea-agents/scripts/rea.mjs`;
- execução com `HOME=/tmp/playmemories-rea-home`, sem `rea setup`, atualização ou alteração da instalação vizinha.

`rea --version`, `--help`, `doctor` e `capabilities` funcionaram. O catálogo reportou 153 comandos CLI e 207 ferramentas MCP. O `doctor` marcou o ambiente como não saudável para análise profunda: Hopper, Ghidra, IDA, JADX e Kuna não estão configurados; a identidade de skill também não está instalada. Node e host foram aprovados.

## Capacidades úteis para um pacote Sony

Sem executar o alvo, o REA expõe operações pertinentes como inventário/extração segura de artefatos, inspeção de layout binário, recursos PE, artefatos .NET/CLI, strings, SQLite e `objdump`. A aplicabilidade real depende do formato do instalador e dos componentes extraídos. O REA não transforma, sozinho, um PE nativo em fonte legível.

No Discovery 02, o REA foi aplicado estaticamente ao `PMHOME_5501DL.exe`. `inspect-artifact` confirmou formato PE e SHA-256; `inspect-pe-resources` confirmou PE32 x86, 45 recursos em 96 entradas e relações de ícones, sem executar o alvo. `inspect-binary-layout` não pôde prosseguir porque o backend Python isolado (pwntools 4.15.0, pyelftools 0.33 e Unicorn 2.1.2) não está instalado/configurado. Nenhuma dependência foi instalada.

## Limitações e backends

- PE nativo: inventário, recursos e layout podem ser inspecionados; decompilação requer backend apropriado.
- .NET/CLI: há inspeção estática de identidade, membros, strings CIL e limites nativos sem carregar o assembly.
- instaladores/contêineres: a extração depende do formato e das ferramentas disponíveis; não se deve inferir suporte antes da identificação.
- bancos SQLite: a CLI declara requisito Node 24.15+ ou 26+ para inspeção; o Node 24.22.1 atende, mas não há banco Sony para testar.
- análise dinâmica, debugger, Frida e captura de processos estão fora desta etapa.

## Decisão sobre Ghidra

Ghidra não é necessário no Discovery 02. O PE disponível é principalmente wrapper IExpress/downloader, e os módulos que responderiam às perguntas de catálogo, miniaturas e metadados não estão presentes. Decompilar o wrapper tem baixo benefício. Caso o payload legítimo seja obtido, uma solicitação específica deve partir de `PMBBrowser.exe`, `PMBContentAnalyzer.exe`, `PMBMPThumb.exe` ou de uma DLL de persistência identificada no novo inventário, contendo:

- componente e pergunta exatos a investigar;
- versão do Ghidra compatível com o REA (o diagnóstico pede Ghidra 12.1.x);
- instalação extraída e isolada no novo workspace, com `GHIDRA_INSTALL_DIR` local;
- estimativa antes do download para armazenamento, RAM, CPU e tempo;
- limites de análise e descarte dos projetos gerados.

Nenhuma ferramenta pesada foi instalada.

