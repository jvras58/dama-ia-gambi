# Dama IA Gambi

Sistema que observa um tabuleiro de damas real pela câmera de um telefone, reconstrói o jogo no PC e usa LLMs servidas por um hub [Gambi](https://www.gambi.sh/pt-br/) para jogar ou aconselhar, com um Minimax como juiz e apoio.

**Estado atual**: marcos M0 a M2 concluídos. A partida já pode ser jogada pela tela do telefone ou do PC, por toque, contra o Minimax ou uma LLM do Gambi, e também no terminal. A leitura do tabuleiro real pela câmera (M3) tem o código pronto, mas a calibração ainda não é confiável com o tabuleiro e a luz reais, então ficou de lado por enquanto; a detecção de lances pela câmera (M4) não existe.

## Como rodar

```bash
uv sync
uv run pytest
uv run dama --help
```

Antes de entregar uma mudança, os três precisam passar:

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

Partida só com o Minimax, sem precisar do Gambi:

```bash
uv run dama simular --brancas minimax --pretas minimax:2
```

Com LLMs, primeiro suba o Gambi (hub, sala e ao menos um participante com modelo) e confira. O projeto foi validado com o Gambi 0.7.2; para atualizar, use `gambi self update`. Ao entrar com um participante, o `--model` precisa ser o nome exato do modelo (por exemplo `llama3.2:latest`).

```bash
uv run dama checar-gambi --hub http://localhost:3000 --sala CODIGO
```

```bash
uv run dama simular --brancas llm:ID_DO_PARTICIPANTE --pretas minimax --sala CODIGO
```

Cada lado aceita `minimax`, `minimax:<profundidade>`, `llm:*` (qualquer participante), `llm:<id-do-participante>` ou `llm:model:<nome>`. As opções também podem vir do arquivo `.env` (veja `.env.example`). Rodar `checar-gambi` antes da partida aquece os modelos; a primeira resposta de um modelo local pode passar de um minuto.

## Jogar pela tela

```bash
uv run dama serve
```

O terminal mostra o endereço `https://<ip>:8443` e um QR code. Abra no telefone, na mesma rede Wi-Fi, ou no navegador do PC. O certificado é autoassinado, então o navegador avisa que a conexão não é segura: escolha "Avançado" e siga para o site.

Escolha quem joga de cada lado (humano, Minimax em três níveis ou uma LLM do Gambi) e toque em "Nova partida". Toque numa peça para ver para onde ela pode ir e depois no destino; numa captura em sequência, toque em cada casa de pouso. "Dica" pede uma sugestão e "Desfazer" volta o seu último lance. Para os lados LLM é preciso subir o Gambi antes; o passo a passo está em [docs/como-subir.md](docs/como-subir.md).

## Câmera do telefone (em pausa)

A leitura do tabuleiro real fica em `https://<ip>:8443/?papel=camera`. Ela ainda não é confiável: a calibração falhou com o tabuleiro real em fundos e luzes diferentes. O fluxo é:

1. Arraste os 4 pontos até as linhas da grade caírem sobre as casas e confirme.
2. Monte a posição inicial e toque em "Calibrar cores". O tabuleiro pode estar com a casa escura ou com a casa clara à esquerda de cada jogador; no segundo caso a leitura é espelhada.
3. O tabuleiro reconhecido aparece na página; casas em dúvida ficam com borda vermelha.

Um segundo aparelho pode acompanhar abrindo o mesmo endereço com `?papel=espectador`.

Para a leitura pausar quando houver uma mão sobre o tabuleiro, baixe o modelo de mão do MediaPipe (7,8 MB, uma vez):

```bash
uv run dama baixar-modelo
```

## Modos de jogo

- **IA × IA** — duas LLMs (ou LLM × Minimax) jogam; um operador move as peças e a câmera confirma.
- **Jogador assistido × Humano** — a IA sugere lances a um dos jogadores.

## Mapa dos documentos

O projeto segue desenvolvimento orientado a especificação (SDD).

| Onde | O quê |
|---|---|
| [AGENTS.md](AGENTS.md) | Instruções para agentes de código: comandos, fluxo e convenções. |
| [docs/como-subir.md](docs/como-subir.md) | Passo a passo para subir o jogo, o Gambi e o Ollama, e para atualizar o Gambi. |
| [docs/constituicao.md](docs/constituicao.md) | Princípios que valem para todo o projeto. |
| [docs/adr/](docs/adr/README.md) | Decisões de arquitetura e seus motivos. |
| [specs/001-dama-ia-gambi/spec.md](specs/001-dama-ia-gambi/spec.md) | O quê e por quê: requisitos e critérios de aceitação. |
| [specs/001-dama-ia-gambi/plan.md](specs/001-dama-ia-gambi/plan.md) | Como: stack, módulos, testes, marcos. |
| [specs/001-dama-ia-gambi/tasks.md](specs/001-dama-ia-gambi/tasks.md) | Tarefas ordenadas, com critério de pronto. |
| `tests/fixtures/` | Imagens de referência do tabuleiro real. |

## Convenções de código

Registradas nos ADRs [0009](docs/adr/0009-convencoes-de-codigo.md) e [0010](docs/adr/0010-docstrings-no-lugar-de-comentarios.md):

- Sem `__init__.py`; `dama` é um pacote de namespace.
- Imports sempre completos (`from dama.regras.tipos import Lance`), nunca relativos.
- Todo valor ajustável fica em `Settings` ([src/dama/config.py](src/dama/config.py)) e pode ser trocado por variável `DAMA_*` ou pelo `.env`.
- Vocabulários fechados são enums; funções são todas anotadas e o `mypy --strict` passa em `src/`.
- Todo módulo, classe e função tem docstring; não há comentários soltos. O teste `tests/test_convencoes.py` garante isso.

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
  config.py                       toda a configuração (Settings)
  cli.py
  regras/  minimax/  llm/  jogo/    prontos
  visao/                          localização, classificação, mão, pipeline
  web/                            servidor HTTPS, WebSocket e a página (static/)
tests/
  apoio/                          servidor Gambi falso e fotos sintéticas do tabuleiro
  fixtures/
```
