# 0007 — LLM via Gambi escolhe o lance por índice numa lista de lances legais

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: RF-LLM da [spec 001](../../specs/001-dama-ia-gambi/spec.md); [ADR 0008](0008-papeis-do-minimax.md)

## Contexto

As jogadas vêm de LLMs servidas por um hub [Gambi](https://www.gambi.sh/pt-br/) na rede local. Segundo a documentação lida em 2026-11-10:

- O hub expõe uma API compatível com OpenAI em `http://<host>:3000/rooms/<CODIGO>/v1`, com Responses API (preferida) e Chat Completions.
- Não há SDK oficial para Python; o caminho indicado é o cliente `openai`.
- O campo `model` aceita `*`/`any`, `model:<nome>` ou o ID de um participante.
- O hub não tem autenticação.
- Tool calling, saída estruturada e entrada de imagem **não são documentados**.

Os modelos são os que os participantes da sala tiverem, muitas vezes locais e pequenos, que erram regras e formato com frequência.

## Decisão

- Usar o cliente **`openai`** assíncrono apontado para a sala do Gambi; Responses API com recuo para Chat Completions.
- A LLM **nunca gera um lance livremente**. O motor de regras calcula os lances legais, o prompt os apresenta numerados, e a LLM responde com o **número** escolhido e uma frase de motivo.
- A resposta é lida de **texto livre**, sem tool calling nem modo JSON.
- A LLM recebe o tabuleiro **em texto**, nunca imagem.
- Resposta inválida gera até 2 novas tentativas; depois disso, ou em erro do hub, joga-se o melhor lance do Minimax, marcado como fallback.
- Com um único lance legal, a LLM não é chamada.

## Alternativas consideradas

- **LLM escreve o lance em notação livre** — modelos pequenos produzem lances ilegais o tempo todo.
- **Tool calling ou saída estruturada** — mais limpo, mas não é garantido pelo Gambi nem por todos os modelos locais.
- **LLM com visão recebendo a foto** — ver [ADR 0004](0004-visao-mediapipe-maos-opencv-cor-calibrada.md).
- **Chamar Ollama ou outro provedor direto** — perde o propósito de usar o Gambi para compartilhar modelos entre máquinas.

## Consequências

- É impossível um lance ilegal entrar no jogo por causa da LLM.
- Funciona com qualquer modelo que consiga escrever um número.
- A partida nunca trava por causa da LLM ou do hub.
- O prompt cresce com o número de lances legais; em damas isso raramente passa de 20 linhas.
- **Revisar se** o Gambi passar a documentar saída estruturada: o leitor de resposta pode ser simplificado.
