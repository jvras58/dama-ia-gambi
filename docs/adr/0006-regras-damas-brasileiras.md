# 0006 — Regras de damas brasileiras

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: RF-REG da [spec 001](../../specs/001-dama-ia-gambi/spec.md)

## Contexto

"Damas" tem variantes com regras bem diferentes. O tabuleiro do projeto é 8×8 e os jogadores são brasileiros.

## Decisão

Implementar as **damas brasileiras**:

- Tabuleiro 8×8, 12 peças por lado, casa `a1` escura, brancas começam.
- Pedra anda para frente e captura para frente e para trás.
- Captura obrigatória, com **lei da maioria**: joga-se a sequência que captura mais peças.
- **Dama voadora**: anda e captura a qualquer distância na diagonal.
- Promoção apenas se o lance termina na última fileira.
- Empate após 20 lances consecutivos de dama sem captura nem movimento de pedra.

## Alternativas consideradas

- **Damas inglesas/americanas** — pedra não captura para trás, dama anda uma casa, sem lei da maioria. Mais simples, mas não é como se joga aqui.
- **Damas internacionais** — tabuleiro 10×10, incompatível com o tabuleiro físico.
- **Várias variantes configuráveis** — multiplica os testes do motor e do Minimax sem necessidade atual.

## Consequências

- O gerador de lances é mais complexo (capturas a distância, lei da maioria) e precisa de testes dedicados.
- O Minimax tem mais lances por posição por causa da dama voadora.
- Suportar outra variante exigirá um novo ADR e um gerador separado.
