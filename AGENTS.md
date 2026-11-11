# AGENTS.md

Instruções para agentes de código que trabalham neste repositório. Para a visão geral do projeto, leia o [README.md](README.md).

## O projeto

Sistema que observa um tabuleiro de damas real pela câmera de um telefone, reconstrói o jogo no PC e usa LLMs servidas por um hub Gambi para jogar ou aconselhar, com um Minimax como juiz e apoio. Regras: damas brasileiras.

Estado: marcos M0 a M2 prontos (regras, Minimax, integração com o Gambi, partidas no terminal). Câmera (M3), interface web (M4) e acabamento (M5) estão por fazer. O andamento fica em [specs/001-dama-ia-gambi/tasks.md](specs/001-dama-ia-gambi/tasks.md).

## Comandos

```bash
uv sync
```

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run ruff format .
```

```bash
uv run mypy
```

```bash
uv run dama simular --brancas minimax --pretas minimax:2
```

- Use sempre `uv run`; não há `python` no PATH.
- Uma mudança só está pronta quando `pytest`, `ruff check .` e `mypy` passam.
- Dependência nova entra com `uv add` (ou `uv add --dev`), nunca editando o `uv.lock` à mão.

## Fluxo de trabalho (SDD)

O projeto segue desenvolvimento orientado a especificação. A ordem importa:

1. **Spec antes do código.** Mudou o requisito? Atualize [spec.md](specs/001-dama-ia-gambi/spec.md) primeiro.
2. **Plano e tarefas.** O como fica em [plan.md](specs/001-dama-ia-gambi/plan.md); o trabalho é feito tarefa por tarefa de [tasks.md](specs/001-dama-ia-gambi/tasks.md), marcando `[x]` ao concluir.
3. **Decisão cara de reverter vira ADR** em [docs/adr/](docs/adr/README.md), com o próximo número e uma linha no índice. ADR aceito não é editado para mudar a decisão; cria-se outro que o substitui.
4. **Funcionalidade nova** ganha a própria pasta `specs/NNN-nome/` com `spec.md`, `plan.md` e `tasks.md`.

Os princípios que valem para tudo estão em [docs/constituicao.md](docs/constituicao.md). Os que mais afetam o código:

- O estado do jogo é sempre legal: todo lance passa pelo motor de regras, venha de onde vier.
- A partida nunca trava por causa de terceiros: se a LLM ou o hub falham, o Minimax joga.
- O núcleo (`regras/`, `minimax/`) é puro e testável, sem rede.
- Tudo roda local; nada do usuário sai da máquina.

## Convenções de código

Decididas nos ADRs [0009](docs/adr/0009-convencoes-de-codigo.md) e [0010](docs/adr/0010-docstrings-no-lugar-de-comentarios.md). São obrigatórias, e parte delas é cobrada por [tests/test_convencoes.py](tests/test_convencoes.py).

- **Sem `__init__.py`.** `dama` é um pacote de namespace.
- **Imports sempre completos**: `from dama.regras.tipos import Lance`. Nunca `from .tipos import ...`.
- **Valor ajustável vai em `Settings`** ([src/dama/config.py](src/dama/config.py)), com docstring de atributo, e entra também no [.env.example](.env.example). Nada de constante de ajuste solta em módulo. O código lê de `obter_config()`.
- **Vocabulário fechado é `StrEnum`**, não string solta. `dict` com forma conhecida é `TypedDict`.
- **Tudo anotado.** `mypy --strict` passa em `src/`; nos testes, as assinaturas são anotadas.
- **Todo módulo, classe e função tem docstring**, incluindo funções privadas, aninhadas e de teste.
- **Sem comentários soltos.** A explicação vai na docstring. Só diretivas de ferramenta são aceitas (`# fmt: skip`, `# noqa`, `# type:`).
- **Idioma**: nomes, docstrings e mensagens em português. No código, sem acentos; nos documentos Markdown, com acentos.
- **Linhas de até 100 colunas**, formatadas pelo `ruff format`.

O que continua como constante `Final` no código, por não ser ajuste: geometria do tabuleiro, codificação das peças em inteiros, códigos HTTP do hub, expressões regulares do parser e o texto do prompt.

## Mapa do código

| Pasta | O que faz |
|---|---|
| `src/dama/config.py` | Toda a configuração (`Settings`, prefixo `DAMA_`). |
| `src/dama/regras/` | Tabuleiro, gerador de lances, partida. Puro. |
| `src/dama/minimax/` | Avaliação, busca alfa-beta, análise e rótulos do juiz. |
| `src/dama/llm/` | Cliente Gambi, prompt, parser e jogador com fallback. |
| `src/dama/jogo/` | Controladores, orquestrador da partida, persistência. |
| `src/dama/cli.py` | Comandos `dama simular`, `dama checar-gambi`, `dama serve`. |
| `tests/apoio/` | Servidor Gambi falso, usado pelos testes de LLM. |
| `tests/fixtures/` | Fotos de referência do tabuleiro real. |

`src/dama/visao/` e `src/dama/web/` ainda não existem; nascem no M3 e no M4.

## Testes

- Os testes de LLM usam o servidor falso de `tests/apoio/servidor_falso.py`; nenhum teste depende de rede ou de um hub real.
- Quando um teste de regras falhar numa posição montada à mão, confira a posição antes de mexer no motor. Até aqui, o motor estava certo em todas as vezes.
- Testes que verificam um critério de aceitação da spec levam o código no nome (`test_ca11_...`).

## Gambi

- Validado com o Gambi 0.7.2. O hub expõe uma API compatível com OpenAI em `http://<hub>:3000/rooms/<SALA>/v1`, sem autenticação.
- O cliente `openai` instalado usa `httpx2`, não `httpx`.
- A LLM nunca inventa lance: recebe a lista numerada de lances legais e responde com o número ([ADR 0007](docs/adr/0007-llm-escolhe-lance-por-indice-via-gambi.md)).
- No modo IA × IA, a análise do Minimax não vai para a LLM; só no modo assistido ([ADR 0008](docs/adr/0008-papeis-do-minimax.md)).
- Ao entrar com um participante, `--model` precisa ser o nome exato (`llama3.2:latest`). A primeira resposta de um modelo local pode passar de um minuto; rode `dama checar-gambi` antes para aquecer.
- Se subir um hub para testar, use `127.0.0.1` e encerre-o ao terminar.

## Git

- Commit só quando o dono do projeto pedir. Não há repositório remoto configurado.
- Mensagens em português, com um título curto e uma lista do que mudou.
- Não entram no repositório: `.env`, `dados/` (partidas salvas), `modelos/` e caches.
