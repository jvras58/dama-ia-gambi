# 0008 — Minimax como juiz, fallback, jogador e analista

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: RF-MMX, RF-LLM-03a, RF-MOD-01, RF-MOD-07 da [spec 001](../../specs/001-dama-ia-gambi/spec.md); [ADR 0007](0007-llm-escolhe-lance-por-indice-via-gambi.md)

## Contexto

Em damas 8×8, um Minimax com poda alfa-beta joga muito melhor que uma LLM. O objetivo do projeto, porém, é ter LLMs jogando. O dono do projeto propôs que a LLM recebesse os dados do Minimax para fundamentar a decisão. Se isso valesse em todos os modos, uma partida entre duas LLMs viraria Minimax contra Minimax com narração.

## Decisão

O Minimax tem quatro papéis, e o que a LLM recebe depende do modo:

| Papel | Onde | O que faz |
|---|---|---|
| **Juiz** | Todos os modos | Avalia cada lance jogado e o rotula (`melhor`, `bom`, `duvidoso`, `erro`); gera um resumo por lado ao fim. Não interfere. |
| **Fallback** | Lados de LLM | Fornece o lance quando a LLM ou o hub falham. |
| **Jogador** | IA × IA | Pode controlar um lado (LLM × Minimax, Minimax × Minimax). |
| **Analista** | Modo assistido | Entrega pontuação e linha prevista de cada lance à LLM conselheira, que escolhe e explica. |

- No **IA × IA**, a LLM **não** recebe a análise do Minimax.
- No **modo assistido**, recebe, porque ali o que importa é a qualidade do conselho.

Implementação: negamax com alfa-beta, aprofundamento iterativo e quiescência em capturas, em Python puro, rodando em processo separado.

## Alternativas consideradas

- **Sem Minimax, só LLM** — sem fallback de qualidade e sem como medir se a LLM jogou bem.
- **Minimax como analista em todos os modos** — tira o sentido da disputa entre modelos.
- **Minimax decide e a LLM só explica** — mais forte, mas a LLM deixa de jogar.
- **Motor de damas externo** — os existentes raramente seguem as regras brasileiras, e isso adicionaria dependência binária.

## Consequências

- Dá para comparar modelos de forma objetiva (rótulos do juiz) e ter um adversário de força conhecida.
- O conselho do modo assistido fica forte e explicado.
- Há mais um componente para escrever e testar, e ele precisa ser rápido o bastante em Python puro.
- A avaliação do juiz é a opinião de um motor simples e de profundidade limitada, não a verdade.
- **Revisar se** a busca não alcançar a profundidade planejada no tempo previsto (tarefa T111).
