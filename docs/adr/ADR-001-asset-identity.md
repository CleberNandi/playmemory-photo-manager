# ADR-001 — Identidade de Asset

- Status: Aceito
- Data: 2026-10-23

## 1. Contexto

O gerenciador cataloga mídia local cujos nomes, caminhos e volumes podem mudar fora da aplicação. Cópias byte a byte podem representar ocorrências que o usuário deseja manter separadas, enquanto hardlinks e movimentos podem representar a mesma ocorrência física. O Discovery não revelou uma identidade Sony reutilizável e o novo produto não precisa reproduzi-la.

## 2. Problema

É necessário manter uma identidade lógica estável sem confundi-la com caminho, inode ou hash; reconciliar mudanças externas; representar indisponibilidade; e evitar fusões destrutivas ou silenciosas entre fotografias distintas.

## 3. Alternativas consideradas

1. **Caminho como identidade.** Simples, mas renomear ou mover cria outro ativo e perde relações.
2. **SHA-256 como identidade.** Detecta igualdade binária, mas força cópias independentes a compartilhar identidade e não representa versões editadas.
3. **Identidade do filesystem como identidade global.** Ajuda em movimentos e hardlinks, mas muda entre cópias/volumes, pode ser reciclada e nem sempre está disponível.
4. **Identificador interno com evidências de reconciliação.** Separa identidade lógica de observações físicas e permite decisões conservadoras. É a escolhida.

## 4. Decisão

Cada `Asset` recebe na criação um UUID aleatório gerado pela aplicação. O UUID é imutável e independente de nome, caminho, inode, hash ou metadata.

`FileLocation` representa uma ocorrência observada em uma `LibraryRoot` por caminho relativo. Um Asset pode ter zero ou mais localizações. Caminhos absolutos são derivados da raiz e nunca compõem a identidade do Asset.

SHA-256 é uma evidência verificada e opcional. Dois caminhos com o mesmo SHA-256 são registrados como Assets distintos por padrão. A aplicação pode agrupá-los como duplicatas exatas e oferecer uma futura ação explícita de consolidação, mas não os funde automaticamente. Uma nova localização só é anexada a um Asset existente automaticamente quando a continuidade da mesma ocorrência física é demonstrada, na mesma raiz, por file-id estável, desaparecimento do caminho anterior na mesma varredura e atributos compatíveis. Isso reduz o risco de reutilização de inode; qualquer ambiguidade produz candidato, não alteração.

Versões da mesma captura — RAW/JPEG, original/editada, exportações e transcodificações — são Assets distintos. Uma relação de versões fica adiada até haver casos de uso e semântica claros; semelhança visual, basename ou metadata coincidente não criam essa relação.

Ao observar caminho externo renomeado ou movido:

- mesma identidade estável do filesystem, raiz disponível, caminho anterior desaparecido no mesmo ciclo e atributos compatíveis: atualizar a `FileLocation`, preservando histórico observacional;
- tamanho + SHA-256 verificado, mas sem identidade estável: criar candidato de reconciliação para confirmação, sem religação automática;
- somente nome, mtime, metadata ou hash perceptual: não religar automaticamente.

Uma localização fica `offline` quando a raiz inteira está indisponível e `missing` apenas após varredura bem-sucedida de uma raiz disponível. Ausência temporária não remove Asset, anotações ou histórico.

Hardlinks detectados pelo mesmo identificador de filesystem na mesma raiz são múltiplas `FileLocation` do mesmo Asset. Symlinks não são seguidos por padrão. Se uma raiz permitir segui-los futuramente, o link é registrado como localização com tipo e destino observados; ciclos, escapes da raiz e links quebrados são rejeitados ou marcados, nunca usados para fusão por si só.

## 5. Justificativa

A política protege a intenção do usuário: nenhum fato técnico isolado decide que duas fotografias são o mesmo objeto lógico. UUID mantém relações estáveis; `FileLocation` absorve mobilidade; inode/file-id e SHA-256 permanecem evidências adequadas ao seu alcance. A decisão favorece falsos negativos revisáveis sobre falsos positivos que misturariam anotações e álbuns.

## 6. Invariantes

- `Asset.id` é imutável, interno e não derivado de conteúdo ou caminho.
- Cada `FileLocation` pertence a exatamente um Asset.
- `(library_root_id, normalized_relative_path)` é único entre localizações ativas.
- SHA-256 só recebe estado `verified` após leitura integral bem-sucedida.
- Mesmo SHA-256 não implica mesmo Asset.
- Nenhuma reconciliação por nome, mtime, metadata ou similaridade é automática.
- Uma raiz offline não transforma suas localizações em ausentes.
- Uma versão editada ou convertida nunca substitui silenciosamente o Asset de origem.
- Symlinks não atravessam a fronteira configurada da raiz por padrão.

## 7. Consequências

O catálogo pode conter Assets duplicados até revisão explícita, o que é intencional. Scanner e reconciliador precisarão registrar qualidade/origem das evidências. A separação suporta múltiplas localizações e volumes offline, mas exige estado de raiz e observações de filesystem. Consolidação e divisão de Assets demandarão operações auditáveis futuras.

## 8. Casos de teste futuros

- renomeio na mesma raiz preserva Asset quando file-id é estável;
- cópia byte a byte em outro caminho cria outro Asset e um candidato de duplicidade;
- movimento entre volumes não religa sem confirmação;
- dois hardlinks tornam-se duas localizações do mesmo Asset;
- symlink quebrado, ciclo e destino fora da raiz não são seguidos;
- raiz desmontada marca localizações offline, não missing;
- arquivo removido em raiz disponível torna-se missing sem apagar o Asset;
- substituição no mesmo caminho por bytes diferentes cria nova observação e não reutiliza identidade silenciosamente;
- RAW e JPEG com timestamp/basename iguais permanecem Assets distintos.

## 9. Questões adiadas

- UX e auditoria de consolidar ou separar Assets;
- relação tipada entre original, derivado, RAW+JPEG e burst;
- identidade portátil entre catálogos/dispositivos;
- política de retenção do histórico de caminhos;
- integração futura com evidências do Duplicate Lab.
