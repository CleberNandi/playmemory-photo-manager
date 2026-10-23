# Revisão do photoOrganizer

## Escopo e licença

Revisão somente leitura de `/home/arch-nandi/Workspace/personal/photoOrganizer`. O diretório não é um repositório Git e não contém `LICENSE`, `COPYING` ou `NOTICE`; portanto, **não há permissão identificada para copiar ou derivar código**. Apenas ideias genéricas podem ser reaproveitadas até que o titular esclareça a licença.

## Arquitetura observada

É um script Python simples, não uma biblioteca catalogadora:

- `main.py`: `PhotoOrganizer` encontra JPEG/JPG no diretório corrente, abre EXIF com Pillow, lê `DateTimeOriginal` e move o arquivo para `AAAA/AAAA-MM-DD` relativo ao diretório de execução;
- `photo_duplicated.py`: script independente, com caminho Windows pessoal fixo, que calcula MD5 lendo arquivos inteiros em memória e imprime grupos duplicados;
- `pyproject.toml`: Python 3.10–3.11, Pillow 9.3, PyInstaller 5.7 e NetworkX 3; não há uso aparente de NetworkX nos arquivos analisados;
- `build/` e `dist/main.exe`: artefatos PyInstaller já presentes; não foram executados;
- `tests/`: contém apenas `__init__.py`; não há testes funcionais.

## Funcionalidade reaproveitável

A regra `DateTimeOriginal -> ano/dia` é um requisito candidato útil para **planejamento** de importação. Ela não deve ser reutilizada diretamente: o Photo Manager deve apresentar plano, resolver colisões, registrar a sessão, copiar antes de qualquer remoção e permitir política configurável.

## Riscos encontrados

- `DateTimeOriginal` ausente causa falha por fatiamento de `None`;
- a string EXIF não é validada e não trata fuso, precisão ou datas inválidas;
- somente JPEG é considerado e a lista de extensões é manual;
- arquivos são movidos destrutivamente, sem dry-run, rollback, log ou tratamento de colisões;
- o destino é relativo ao processo, não explicitamente configurado;
- imagem/EXIF não são abertos em context manager;
- duplicatas usam MD5 e carregam o arquivo inteiro; não percorrem subdiretórios nem integram o organizador;
- não há catálogo, álbuns, tags, miniaturas, reconciliação ou metadados de vídeo.

## Recomendação

Reaproveitar apenas o conceito de política de destino baseada na data de captura. Não migrar código ou binários nesta etapa. Um futuro importador deve separar `scan -> plan -> confirm -> copy -> verify -> catalog`, preservar origem por padrão e registrar cada resultado.

