# 0009 — Convenções de código: sem `__init__.py`, valores em `Settings`, tipagem forte, imports completos

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: [ADR 0002](0002-python-312-com-uv.md), [constituição](../constituicao.md)

## Contexto

Os marcos M0 a M2 foram escritos com `__init__.py` em cada pasta, imports relativos (`from ..regras.tipos import ...`), valores soltos no topo dos módulos (`LIMITE_BOM = 30`, `VALOR_PEDRA = 100`) e vocabulários como strings (`"melhor"`, `"llm"`, `"em_jogo"`). O dono do projeto pediu outra organização antes de o código crescer com a câmera e a interface.

## Decisão

1. **Sem `__init__.py`.** `dama` e suas subpastas são pacotes de namespace. O `pyproject.toml` declara `namespace = true` para o `uv_build`, e o pytest roda com `--import-mode=importlib`.
2. **Imports sempre completos**: `from dama.regras.tipos import Lance`. Import relativo é erro de lint (`ban-relative-imports = "all"` no ruff).
3. **Todo valor ajustável fica em `dama/config.py`**, na classe `Settings` do pydantic-settings, e pode ser trocado por variável `DAMA_*` ou pelo `.env`. Isso inclui limites dos rótulos do juiz, pesos da avaliação, pontuações da busca, tempos e tentativas da LLM, limite de empate e padrões da simulação. O código lê de `obter_config()`.
4. **Vocabulários fechados são enums** (`StrEnum`): `Rotulo`, `Origem`, `Estado`, `Modo`, `Evento`, `TipoControlador`, `Protocolo`, `TipoErro`, `Lado`, `Resultado`.
5. **Tipagem forte**: toda função anotada, `TypedDict` no lugar de `dict` solto, e `mypy --strict` limpo em `src/`. O ruff exige anotações (`ANN`) também nos testes.

## O que continua no código

Nem toda constante é configuração. Ficam no código, anotadas com `Final`:

- **Geometria e codificação do jogo**: tabuleiro 8×8, 32 casas, direções, e os inteiros das peças (`PEDRA = 1`, `PRETA = -1`). A busca multiplica peça por cor; trocar esses valores por configuração quebraria o motor, e um `IntEnum` deixaria a busca mais lenta.
- **Fatos de protocolo**: códigos HTTP do hub Gambi, expressões regulares do parser, versão do formato do arquivo de partida.
- **Texto do prompt**: é conteúdo, e muda junto com o parser que lê a resposta.

## Alternativas consideradas

- **`Settings` aninhado por área** (`config.minimax.profundidade`, variável `DAMA_MINIMAX__PROFUNDIDADE`) — mais organizado, mas mudaria o nome das variáveis já documentadas. Os campos ficam planos, com prefixo por área.
- **Peças e cores como `IntEnum`** — mais expressivo, porém `-vez` deixaria de ter o tipo do enum e cada operação no laço da busca ficaria mais cara.
- **`mypy --strict` também nos testes** — hoje gera cerca de 30 avisos, quase todos por acesso a valores opcionais em asserções. Fica para depois.

## Consequências

- Mudar um peso ou um limite não exige editar código: basta o `.env`.
- Valores incoerentes (por exemplo, limite de "bom" acima do de "duvidoso") são recusados na partida do programa, pelo validador de `Settings`.
- As camadas `regras/` e `minimax/` passam a importar `dama.config`. Continuam sem rede e sem disco além da leitura única do `.env`.
- A leitura da configuração na avaliação não mudou o desempenho da busca: profundidade 7 na posição inicial em cerca de 0,8 s, antes e depois.
- Sem `__init__.py`, uma pasta vazia em `src/dama/` não é pacote nem aparece no git; `visao/` e `web/` passam a existir quando tiverem código.
