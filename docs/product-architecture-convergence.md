# Convergência de produto e arquitetura desktop

## Objetivo e limites

Este documento orienta a convergência do PlayMemories Photo Manager em um único produto
local-first. Complementa a ADR-004 sem implementar interface, Electron, APIs ou integração com
laboratórios. As ADRs 001–003 continuam normativas para identidade, proveniência e organização.

## Papéis e fronteiras

| Componente | Papel | Não é |
|---|---|---|
| Photo Manager | Produto e autoridade sobre domínio, catálogo, segurança e operações locais | SaaS ou agregador de runtimes dos Labs |
| Sony Lab | Fonte independente de requisitos observados e referências de UX | Dependência, código-base ou especificação normativa |
| Duplicate Lab | Ambiente independente para experimentar e homologar capacidades de duplicidade | Schema, runtime ou autoridade de identidade do produto |
| Product UX Discovery | Validação de jornadas, hierarquia, estados, acessibilidade e feedback | Autorização implícita para mutações em arquivos |

O módulo interno futuro de duplicatas recebe referências estáveis e fatos mínimos aprovados do
catálogo. Ele produz evidências, grupos candidatos e recomendações. Não acessa o schema do Lab,
não funde Assets, não remove arquivos e não decide a variante preferida sem política e revisão
humana. A detecção nunca autoriza fusão ou exclusão automática. Ações físicas continuam
pertencendo aos casos de uso seguros e auditáveis do produto. O Duplicate Lab não é executado nem
distribuído como serviço ou dependência necessária do aplicativo final.

## Critérios de homologação de capacidades dos Labs

Uma capacidade só converge para o produto após demonstrar:

1. requisito e jornada de usuário explícitos;
2. contrato independente do runtime, caminhos e schema do Lab;
3. fixtures sintéticas e testes determinísticos, inclusive falsos positivos e falhas;
4. compatibilidade com ADR-001, ADR-002 e ADR-003;
5. ausência de mutação implícita, com plano, confirmação e auditoria quando aplicável;
6. limites de desempenho e consumo medidos no perfil local;
7. licenciamento e proveniência adequados para incorporação;
8. comportamento de erro, cancelamento e retomada definido.
9. seleção nominal dos algoritmos homologados, com versão, parâmetros, corpus e evidências
   preservados;
10. rejeição demonstrada dos falsos positivos conhecidos, sem promover módulos experimentais por
    expectativa ou resultado isolado.

Resultados Sony são requisitos candidatos sustentados por evidência. Resultados do Duplicate Lab
são evidências técnicas candidatas. Nenhum deles entra no produto por paridade automática.

## Estratégia progressiva

1. Consolidar catálogo, ingestão controlada e contratos de leitura existentes.
2. Executar Product UX Discovery com dados sintéticos e definir os fluxos prioritários.
3. Homologar o shell por uma PoC descartável, sem acoplar o domínio ao Electron.
4. Construir a primeira interface sobre casos de uso estreitos e seguros.
5. Introduzir thumbnails e tarefas longas com medições antes de separar processos adicionais.
6. Homologar capacidades do Duplicate Lab individualmente e incorporá-las como módulos internos.
7. Revisar o escopo funcional contra os resultados do Sony Lab e do Product UX Discovery antes de
   homologar o MVP.
8. Somente depois avaliar operações físicas avançadas, sempre com plano e confirmação.

## Critérios da futura PoC Electron

A PoC não faz parte desta atividade. Quando autorizada, deverá produzir evidência reproduzível
para todos os itens abaixo:

1. abrir uma janela Electron contendo frontend React;
2. iniciar e encerrar o backend Python de forma controlada junto ao lifecycle da aplicação;
3. usar comunicação exclusivamente local, autenticada por segredo efêmero e restrita ao processo
   ou usuário, sem escuta em interfaces externas;
4. manter context isolation, renderer sem integração Node e IPC allowlist com privilégios mínimos;
5. tratar falha de bootstrap, crash, timeout, encerramento e processos órfãos;
6. renderizar uma galeria sintética com estados vazio, carregando, sucesso e erro;
7. consultar pelo backend dados reais de um catálogo SQLite sintético e exibi-los na galeria, sem
   fixtures embutidas no renderer nem acesso direto do frontend ao banco;
8. fornecer thumbnails por uma fronteira confinada, sem expor caminhos arbitrários ou permitir
   path traversal;
9. medir tempo de inicialização, memória ociosa e memória durante a galeria em ambiente descrito;
10. iniciar e executar as jornadas avaliadas completamente offline;
11. produzir e avaliar primeiro um pacote experimental para Linux;
12. repetir posteriormente os critérios aplicáveis e validar o empacotamento no Windows;
13. verificar a compatibilidade futura com macOS, plataforma-alvo, sem declarar suporte ou
    homologação antes de teste próprio;
14. avaliar um artefato final que inclua o runtime/backend necessário e não exija instalação
    separada de Python, se a abordagem de empacotamento escolhida conseguir incluí-lo.
15. registrar a avaliação de Tauri como alternativa se Electron falhar em critério crítico ou não
    atingir limites de distribuição, memória ou inicialização definidos para homologação.

A PoC deve registrar versões, hardware, sistema, comandos, métricas e falhas. Aprovação exige que
nenhum critério crítico de segurança ou lifecycle permaneça sem resposta; metas quantitativas de
startup e memória serão definidas após o Product UX Discovery e uma medição-base.

## Segurança e responsabilidade de lifecycle

O shell é responsável por criar a credencial efêmera, iniciar exatamente uma instância do backend,
verificar sua prontidão, encerrar o processo em fechamento normal e realizar término escalonado em
falha ou timeout. O backend restringe a fronteira ao usuário/processo local, valida toda entrada e
não confia no renderer. Se a PoC usar loopback, deve autenticar cada sessão, escolher porta não
previsível e não escutar em interfaces externas; stdio, IPC nativo ou socket local continuam
alternativas. Uma API HTTP não é requisito e só pode ser escolhida mediante justificativa.

## Riscos de distribuição multiplataforma

- diferenças de paths, caixa, Unicode, volumes e permissões entre Linux, Windows e futuro macOS;
- empacotamento conjunto de Node/Electron e Python, tamanho do artefato e compatibilidade nativa;
- assinatura, notarização, reputação do instalador e atualizações seguras por plataforma;
- antivírus, quarentena e regras de firewall afetando subprocesso ou comunicação local;
- codecs e bibliotecas nativas com licenciamento ou ABI específicos;
- processos órfãos, disputa de porta/socket e concorrência sobre o catálogo;
- sandbox, acesso a pastas escolhidas pelo usuário e exposição acidental de caminhos;
- divergência entre ambientes de desenvolvimento e artefatos realmente distribuídos.

Atualização automática e telemetria não são pressupostos. Se forem propostas, exigirão decisões
separadas, consentimento e funcionamento útil sem conexão.

## Dependências do Product UX Discovery

Antes da interface de produção, o Sony Lab e o Product UX Discovery deverão informar, com
evidências rastreáveis e sem impor implementação, ao menos: jornada de seleção de raiz,
primeira catalogação e progresso; biblioteca/galeria e estados de erro; revisão de duplicatas;
vocabulário para Asset versus arquivo/localização; confirmação de operações físicas; acessibilidade
por teclado e leitores de tela; privacidade de paths, GPS e thumbnails; e expectativas por
plataforma. Seus resultados refinam a UI, o escopo do MVP e as metas da PoC, mas não enfraquecem
políticas de segurança nem substituem as ADRs.

## Milestones funcionais do MVP

1. **Catálogo local utilizável:** criar/abrir catálogo, configurar raiz e catalogar arquivos com
   os limites já definidos pelas Foundations.
2. **Biblioteca navegável:** galeria e detalhe com thumbnails regeneráveis, busca/filtros mínimos
   e estados explícitos de indisponibilidade.
3. **Organização segura:** álbuns, tags, rating, favorito, título e descrição sem alterar originais.
4. **Observação e atualização:** nova varredura e apresentação conservadora de mudanças, sem merge
   ou `missing` indevido.
5. **Duplicatas assistidas:** grupos exatos inicialmente, depois candidatos similares somente se
   homologados; nenhuma exclusão ou consolidação automática.
6. **Distribuição desktop:** artefato Linux validado primeiro, validação posterior no Windows,
   operação offline, backup do catálogo e diagnóstico local sanitizado.

Vídeo profundo, cloud, colaboração, multitenancy, sincronização remota, escrita de metadata e
homologação de macOS ficam fora do MVP salvo decisão posterior. Isso não remove macOS como alvo de
compatibilidade da arquitetura.

## Questões pendentes

- mecanismo local definitivo entre shell e backend: stdio/IPC, socket de domínio ou loopback;
- estratégia de empacotamento do Python e bibliotecas nativas;
- metas quantitativas de startup, memória, tamanho e escala da galeria;
- política de atualização e assinatura por plataforma;
- modelo de tarefas longas e necessidade comprovada de worker separado;
- contrato interno e primeira capacidade do módulo de duplicatas;
- limites que disparam a avaliação comparativa de Tauri;
- escopo detalhado e resultados do Product UX Discovery.
