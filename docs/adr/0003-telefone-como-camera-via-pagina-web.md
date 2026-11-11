# 0003 — Telefone como câmera via página web; processamento no PC

- **Status**: Aceito
- **Data**: 2026-11-10
- **Relacionado**: RF-CAP, RF-UI, RNF-04, RNF-06 da [spec 001](../../specs/001-dama-ia-gambi/spec.md)

## Contexto

O tabuleiro é filmado por um telefone ou tablet, e o processamento precisa estar no PC, onde ficam o Python, o MediaPipe e o acesso ao hub Gambi. Navegadores móveis só liberam a câmera em contexto seguro (HTTPS).

## Decisão

- O telefone abre uma **página web servida pelo próprio servidor Python** na rede local. Não há app nativo.
- A página envia frames JPEG por **WebSocket** (cerca de 5 fps) e recebe estado, alertas e sugestões.
- O servidor usa **HTTPS com certificado autoassinado**, gerado na primeira execução. `mkcert` fica documentado como alternativa.
- O front-end é **HTML/CSS/JS puro**, sem etapa de build.
- Toda a visão roda no PC; o telefone não processa imagem.

## Alternativas consideradas

- **App nativo Android/iOS** — muito mais trabalho e duas plataformas.
- **MediaPipe no navegador do telefone (Tasks Web)** — tiraria o processamento do Python e dependeria do desempenho de cada aparelho.
- **App de câmera IP no telefone (RTSP/MJPEG)** — exige instalar app de terceiros e não oferece interface de volta ao jogador.
- **WebRTC** — menor latência, mas com complexidade desnecessária para 5 fps em rede local.

## Consequências

- Funciona em qualquer telefone com navegador atual, sem instalar nada.
- O usuário vê um aviso de certificado na primeira vez.
- Servidor e hub Gambi não têm autenticação: uso só em rede local confiável.
- Risco: o Safari do iOS pode recusar WebSocket seguro com certificado autoassinado; a tarefa T301 verifica isso antes do restante.
