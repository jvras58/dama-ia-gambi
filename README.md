# Dama IA Gambi

Sistema que observa um tabuleiro de damas real pela câmera de um telefone, reconstrói o jogo no PC e usa LLMs servidas por um hub [Gambi](https://www.gambi.sh/pt-br/) para jogar ou aconselhar, com um Minimax como juiz e apoio.

**Estado atual**: marcos M0 a M2 concluídos. Já é possível jogar partidas no terminal entre LLMs (via Gambi) e o Minimax. Câmera e interface web ainda não existem.

## Como rodar

```bash
uv sync
uv run pytest
uv run dama --help
```

Partida só com o Minimax, sem precisar do Gambi:

```bash
uv run dama simular --brancas minimax --pretas minimax:2
```

Com LLMs, primeiro suba o Gambi (hub, sala e ao menos um participante com modelo) e confira:

```bash
uv run dama checar-gambi --hub http://localhost:3000 --sala CODIGO
```

```bash
uv run dama simular --brancas llm:ID_DO_PARTICIPANTE --pretas minimax --sala CODIGO
```

Cada lado aceita `minimax`, `minimax:<profundidade>`, `llm:*` (qualquer participante), `llm:<id-do-participante>` ou `llm:model:<nome>`. As opções também podem vir do arquivo `.env` (veja `.env.example`). Rodar `checar-gambi` antes da partida aquece os modelos; a primeira resposta de um modelo local pode passar de um minuto.

## Modos de jogo

- **IA × IA** — duas LLMs (ou LLM × Minimax) jogam; um operador move as peças e a câmera confirma.
- **Jogador assistido × Humano** — a IA sugere lances a um dos jogadores.

## Mapa dos documentos

O projeto segue desenvolvimento orientado a especificação (SDD).

| Onde | O quê |
|---|---|
| [docs/constituicao.md](docs/constituicao.md) | Princípios que valem para todo o projeto. |
| [docs/adr/](docs/adr/README.md) | Decisões de arquitetura e seus motivos. |
| [specs/001-dama-ia-gambi/spec.md](specs/001-dama-ia-gambi/spec.md) | O quê e por quê: requisitos e critérios de aceitação. |
| [specs/001-dama-ia-gambi/plan.md](specs/001-dama-ia-gambi/plan.md) | Como: stack, módulos, testes, marcos. |
| [specs/001-dama-ia-gambi/tasks.md](specs/001-dama-ia-gambi/tasks.md) | Tarefas ordenadas, com critério de pronto. |
| `tests/fixtures/` | Imagens de referência do tabuleiro real. |

## Fluxo de trabalho

1. Nova funcionalidade: criar `specs/NNN-nome/` e escrever `spec.md`, depois `plan.md`, depois `tasks.md`.
2. Decisão cara de reverter: registrar um ADR em `docs/adr/`.
3. Implementar tarefa por tarefa, marcando `[x]` no `tasks.md`.
4. Mudou o requisito: atualizar a spec antes do código.

## Estrutura

```
docs/
  constituicao.md
  adr/
specs/
  001-dama-ia-gambi/
    spec.md  plan.md  tasks.md
src/dama/
  regras/  minimax/  llm/  jogo/    prontos
  visao/  web/                    a implementar
tests/
  fixtures/
```
