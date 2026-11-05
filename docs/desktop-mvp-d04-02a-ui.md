# D04-02A — UI de preparação

Base: `85cb1ce535374f666947ad7804114bace6059f6d`. Esta entrega implementa a
interface de preparação; aplicação e autorização de catalogação são D04-02B.

## Comportamento

- O main acrescenta `cataloging_enabled` às respostas `library:*`, derivado de
  `PLAYMEMORIES_DESKTOP_INGESTION_LAB=1` e desabilitado em demo. Não é autorização:
  os controles de IPC/Python existentes continuam obrigatórios.
- Somente uma biblioteca ativa com essa capacidade apresenta o painel. A chave de
  sessão existente remonta o painel e invalida respostas tardias.
- Seleção e confirmação usam exclusivamente os diálogos nativos já existentes.
  Cancelar o diálogo preserva o estado; nenhum path vem do renderer.
- Preparar consome a seleção local antes da chamada. Falhas não causam retry de
  admissão; exigem nova seleção. Nenhum grant é persistido no renderer.
- Polling de status a cada 250 ms após a resposta anterior, sem consultas
  sobrepostas. Revisões antigas e respostas de outra operação/sessão são ignoradas;
  estado terminal não é substituído por resposta tardia de cancelamento.
- Cancelar mantém a seleção bloqueada até estado terminal confirmado pelo backend.
  Erro de status interrompe polling e conserva bloqueio; reabrir a biblioteca é a
  recuperação conservadora. Não declarar reap a partir de timeout do renderer.
- Só `completed` permite consultar proposta, sempre com página de 50 itens. Cada
  página substitui a anterior, mantendo cursor opaco e memória visual limitada.
  Estado/motivo técnico fixo e caminho relativo são exibidos como texto React.
- A interface informa total desconhecido e limitação estrutural JPEG, sem percentual,
  preview, hash, decodificação ou botão de aplicação. Não cria Assets/FileLocations.

## Verificação manual no KDE (pendente)

Com checkout desta branch e dependências instaladas:

```bash
PLAYMEMORIES_DESKTOP_LIBRARY_LAB=1 PLAYMEMORIES_DESKTOP_INGESTION_LAB=1 pnpm --dir desktop start
```

Usar catálogo de teste fora da pasta de mídia e somente arquivos sintéticos:

1. Sem flag de ingestão e em demo, confirmar ausência do painel.
2. Criar/abrir biblioteca e cancelar seleção e confirmação: nenhuma preparação.
3. Confirmar pasta vazia, preparar e abrir proposta vazia.
4. Preparar pasta com JPEGs baseline sintéticos e formatos excluídos; conferir
   contagens, caminhos relativos, motivos e páginas de até 50 itens.
5. Cancelar durante execução: aguardar encerramento antes de nova seleção.
6. Fechar/trocar biblioteca durante execução, aguardar cleanup e repetir fechamento;
   nenhum resultado anterior deve aparecer na nova sessão.
7. Rejeitar raiz contendo catálogo/cache e confirmar que pasta irmã continua válida.
8. Fechar aplicativo durante execução e verificar ausência de processos órfãos.

Smokes headless não comprovam diálogos KDE nem ausência de órfãos nesse ambiente.
D04-02A continua aguardando auditoria e validação nativa antes de conclusão.

## Evidências deste incremento

- `uv sync --locked`, 554 testes Python, Ruff e formatação: PASS.
- Instalação desktop com lockfile congelado, typecheck, testes, lint e build: PASS.
  O runner usa pnpm 11.25.0; a versão declarada 12.15.0 permanece sem alteração.
- Smoke Electron headless D04-02A IPC e D04-01B: PASS, com árvores sintéticas.
  Execução com `--ozone-platform=headless --disable-gpu --no-sandbox` no runner root;
  não comprova diálogos KDE. Os fluxos de UI são cobertos pelos testes jsdom.
- Nenhuma modificação em Python, banco, originais, dependências ou lockfile.
- Auditoria independente desta UI e smoke manual KDE: pendentes.

## Correções da auditoria de 5e3b087

- MINOR-01: o próximo polling considera `latest.current` após `accept`, nunca o
  payload descartado. Três regressões simulam resposta terminal de outra operação,
  outra sessão e revisão antiga, seguidas de conclusão legítima.
- MINOR-02: botões primários desabilitados usam fundo/borda e texto dos tokens,
  cursor `not-allowed` e ausência de sombra, sem reduzir a opacidade do texto.
  Painel e tabela usam tokens de superfície/borda em lugar de `currentColor`.
- Reauditoria e validação manual KDE permanecem pendentes; nenhuma integração
  em main faz parte desta correção.
- Revalidação desktop: typecheck, 94 testes, lint e build PASS. A primeira
  tentativa teve timeout no teste de inicialização real do backend durante a
  reconstrução do ambiente Python; repetição com ambiente instalado passou.
