# 0002 — Python 3.12 gerenciado com uv

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: [plano 001, seção 2](../../specs/001-dama-ia-gambi/plan.md)

## Contexto

O dono do projeto pediu Python e uv. O `mediapipe` e o `opencv` distribuem binários por plataforma, e versões muito novas do Python costumam demorar a ter suporte. Em 2026-11-10 a máquina de desenvolvimento tinha uv 0.11.8 e Python 3.10 a 3.14 via uv; o `mediapipe 1.2.2` tinha wheel para Windows x64.

## Decisão

- Gerenciar o projeto com **uv** (`pyproject.toml`, `uv.lock`, `uv run`).
- Fixar **Python 3.12** (`requires-python = ">=3.12,<3.13"`).
- Layout `src/` com um único pacote `dama`.

## Alternativas consideradas

- **Python 3.13/3.14** — mais novo, mas com mais risco de dependência binária sem suporte.
- **pip + venv ou Poetry** — contrariam o pedido e não trazem vantagem aqui.

## Consequências

- Ambiente reproduzível com `uv sync`.
- Subir a versão do Python é uma decisão explícita, feita depois de conferir as dependências binárias.
