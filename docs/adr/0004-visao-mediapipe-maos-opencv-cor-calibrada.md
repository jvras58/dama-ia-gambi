# 0004 — Visão: MediaPipe para mãos, OpenCV e cor calibrada para o tabuleiro

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: RF-VIS, RNF-01 da [spec 001](../../specs/001-dama-ia-gambi/spec.md); [plano 001, seção 4.3](../../specs/001-dama-ia-gambi/plan.md)

## Contexto

O pedido original foi usar MediaPipe para ver o tabuleiro. O MediaPipe não traz detector pronto de tabuleiro nem de peças de damas; para isso seria preciso treinar um modelo próprio, com coleta e anotação de imagens.

O tabuleiro real tem cerca de 20 × 20 cm, casas marrom-cobre e brancas, superfície brilhante, vinco no meio, e fica sobre uma mesa clara. As peças são pretas e brancas. A câmera fica em suporte fixo.

## Decisão

Dividir a visão em três partes:

1. **MediaPipe Hand Landmarker** detecta mão sobre o tabuleiro. Enquanto houver mão, não há leitura; o estado só é lido depois que a mão sai e a imagem estabiliza.
2. **OpenCV** localiza o tabuleiro (máscara de saturação e quadrilátero, com ajuste manual dos 4 cantos na tela) e retifica a perspectiva por homografia.
3. **Classificação por cor calibrada**: cada casa escura é classificada como vazia, branca ou preta por luminância e saturação, com referências aprendidas na posição inicial de cada sessão.

O classificador fica atrás de uma interface, para ser trocado sem mexer no resto.

## Alternativas consideradas

- **Modelo MediaPipe customizado (detector ou classificador de peças) desde o início** — exige um conjunto de imagens anotadas antes de existir qualquer resultado. Fica como plano B.
- **Mandar a foto para uma LLM com visão** — lento, caro, impreciso para 32 casas, e o Gambi não documenta suporte a imagem.
- **Marcadores ArUco nos cantos** — localização muito robusta, mas exige imprimir e colar marcadores. Fica como opção se a localização por cor falhar em outras mesas.
- **Câmera na mão** — exigiria relocalizar o tabuleiro a cada frame.

## Consequências

- Não há etapa de treino; a calibração leva segundos e se adapta à luz do momento.
- O MediaPipe tem um papel menor do que o pedido original sugeria, mas é o que torna a detecção de jogadas confiável.
- Sensível a reflexos na superfície brilhante e à mudança brusca de luz.
- A localização automática depende de a mesa ser pouco colorida; o ajuste manual cobre os outros casos.
- **Revisar se** a acurácia por casa ficar abaixo de 99% nas imagens de teste (RNF-01): aí entra o modelo customizado.
