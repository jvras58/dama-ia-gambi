# 0005 — Damas promovidas rastreadas pelo motor de regras, não pela câmera

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: RF-VIS-10, RF-REG-04, RF-REG-09, RF-JOG da [spec 001](../../specs/001-dama-ia-gambi/spec.md); [ADR 0004](0004-visao-mediapipe-maos-opencv-cor-calibrada.md)

## Contexto

Uma dama costuma ser marcada empilhando duas peças. Vista de cima, a pilha é quase idêntica a uma peça só. O motor de regras, por outro lado, sabe exatamente quando uma pedra é promovida.

## Decisão

- A câmera informa apenas **ocupação e cor** de cada casa escura: vazia, branca ou preta.
- O **motor de regras** mantém quais peças são damas.
- Um lance é reconhecido comparando a ocupação observada com a ocupação resultante de cada lance legal.

## Alternativas consideradas

- **Reconhecer a dama pela imagem** (altura da pilha, marca em cima) — pouco confiável de cima e dependente de como cada jogador marca a dama.
- **Peças de dama diferentes** — obrigaria a trocar o jogo de peças.

## Consequências

- A classificação fica com 3 classes, o que a deixa simples e robusta.
- O estado só é correto se a partida for acompanhada desde uma posição conhecida. Começar no meio de um jogo exige editar a posição na tela e marcar as damas.
- Se o sistema perder um lance, o erro precisa de correção manual (desfazer ou forçar o estado).
