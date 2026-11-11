# 0010 — Docstrings no lugar de comentários

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: [ADR 0009](0009-convencoes-de-codigo.md)

## Contexto

Depois do ADR 0009, o código ainda tinha comentários soltos: divisores de seção (`# --- Turno ---`), notas no fim de linha e explicações no meio das funções. Muitas funções, em especial as privadas e os testes, não tinham docstring. O dono do projeto pediu que a explicação fique sempre na docstring.

## Decisão

1. **Todo módulo, classe e função tem docstring**, incluindo funções privadas, aninhadas e de teste.
2. **Nada de comentário solto.** O que precisa ser explicado vai para a docstring da função, da classe ou do módulo a que pertence.
3. **Campos e membros de enum são documentados com docstring de atributo**: uma string logo abaixo do campo. Em `Settings`, o pydantic lê essa string como descrição do campo (`use_attribute_docstrings`).
4. **Constantes de módulo são explicadas na docstring do módulo.**
5. **Diretivas de ferramenta continuam permitidas** (`# fmt: skip`, `# noqa`, `# type:`), porque não são explicação e não têm outra forma de ser escritas.

## Como é garantido

- `ruff` com a regra `D1` cobra docstring em tudo o que é público.
- [tests/test_convencoes.py](../../tests/test_convencoes.py) cobra o resto: docstring em funções privadas e aninhadas, ausência de comentários (via `tokenize`) e ausência de `__init__.py`.

## Alternativas consideradas

- **Só a regra `D1` do ruff** — não cobre funções privadas nem aninhadas, e não existe regra que proíba comentários.
- **Manter comentários curtos dentro das funções** — contraria o pedido e deixa a explicação longe de quem lê a assinatura.

## Consequências

- Quem lê uma função encontra na docstring também as decisões que antes ficavam em comentários no meio do corpo.
- Uma explicação que só faz sentido ao lado de uma linha específica precisa ser reescrita em termos do comportamento da função, ou a linha vira uma função com nome próprio.
- Os testes ficam mais longos: cada um descreve em uma frase o que verifica.
