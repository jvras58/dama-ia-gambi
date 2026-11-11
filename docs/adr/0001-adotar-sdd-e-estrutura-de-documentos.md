# 0001 — Adotar SDD e esta estrutura de documentos

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: [constituição](../constituicao.md)

## Contexto

O projeto junta visão computacional, regras de jogo, um algoritmo de busca e LLMs. Boa parte do código será escrita com ajuda de IA, e sem um documento de referência cada sessão reinterpreta o objetivo.

## Decisão

Usar desenvolvimento orientado a especificação (SDD). Cada funcionalidade tem uma pasta numerada em `specs/` com três documentos, escritos nesta ordem:

1. `spec.md` — o quê e por quê (requisitos e critérios de aceitação).
2. `plan.md` — como (arquitetura, módulos, testes).
3. `tasks.md` — tarefas ordenadas, cada uma com critério de pronto.

Decisões de arquitetura ficam em `docs/adr/`. Princípios que valem para todas as funcionalidades ficam em `docs/constituicao.md`.

```
docs/
  constituicao.md
  adr/NNNN-titulo.md
specs/
  NNN-nome-da-funcionalidade/
    spec.md  plan.md  tasks.md
src/  tests/
```

## Alternativas consideradas

- **Só um README e issues** — pouco para um projeto com tantas decisões interligadas.
- **Ferramenta de SDD com CLI própria (ex.: spec-kit)** — a estrutura adotada é compatível com a dela, mas a ferramenta não é necessária agora.

## Consequências

- Código só é escrito para tarefas que existem em um `tasks.md`.
- Mudança de requisito altera primeiro a spec, depois o plano e as tarefas.
- Há o custo de manter os documentos em dia; um documento desatualizado é pior que nenhum.
