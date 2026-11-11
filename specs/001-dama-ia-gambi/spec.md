# spec.md — Dama IA Gambi

> Especificação 001 (SDD) — versão 0.2, 2026-11-10. Descreve **o quê** e **por quê**. O **como** está em [plan.md](plan.md) e [tasks.md](tasks.md); as decisões, em [docs/adr/](../../docs/adr/README.md); os princípios, na [constituição](../../docs/constituicao.md).

## 1. Visão geral

Sistema que observa um tabuleiro de damas físico pela câmera de um telefone/tablet, reconstrói o estado do jogo (peças brancas e pretas em cada casa) e usa LLMs servidas por um hub [Gambi](https://www.gambi.sh/pt-br/) na rede local para escolher jogadas.

O telefone é só câmera e tela. Todo o processamento (visão, regras, LLM) roda no PC.

### Objetivos

- **O1** — Mapear corretamente peças brancas e pretas de um tabuleiro 8×8 real, ao vivo.
- **O2** — Manter um estado de jogo válido, detectando cada jogada feita no tabuleiro físico.
- **O3** — Obter jogadas de LLMs via Gambi, sempre restritas a lances legais.
- **O4** — Oferecer dois modos: **IA × IA** e **Jogador assistido por IA × Humano**.
- **O5** — Usar um algoritmo **Minimax** como juiz dos lances, fallback, adversário de referência e base do conselho no modo assistido.

### Fora de escopo (v1)

- Braço robótico ou qualquer movimentação automática de peças.
- Jogo online/remoto, contas de usuário, ranking.
- App nativo (Android/iOS). O cliente é uma página web.
- Motor de nível competitivo (tabelas de finais, livro de aberturas). O Minimax da seção 4.5 é um motor simples.
- Treinar ou hospedar LLMs: os modelos são dos participantes da sala Gambi.
- Outros tamanhos de tabuleiro (10×10) e outras variantes de regra.

## 2. Usuários e cenários

| Persona | Quer |
|---|---|
| **Operador** (IA × IA) | Ver duas LLMs se enfrentando num tabuleiro real, movendo as peças conforme o sistema indica. |
| **Jogador assistido** | Jogar contra um amigo recebendo sugestão de lance da IA a cada turno seu. |
| **Oponente humano** | Jogar normalmente; não interage com o sistema. |

### Cenário A — IA × IA

1. Operador sobe o servidor no PC, abre a página no telefone e aponta a câmera para o tabuleiro.
2. Calibra o tabuleiro e confirma a posição inicial.
3. Escolhe qual participante/modelo do Gambi joga de brancas e qual de pretas.
4. A cada turno, o sistema pede o lance à LLM da vez e mostra o lance (origem → destino, capturas) na tela.
5. O operador executa o lance no tabuleiro físico; a câmera confirma que o estado bate com o esperado e passa o turno.
6. Repete até fim de jogo; resultado e histórico ficam disponíveis.

### Cenário B — Jogador assistido × Humano

1. Mesma preparação; o jogador assistido escolhe sua cor e o modelo conselheiro.
2. No turno do assistido, o sistema mostra a sugestão da LLM (lance + justificativa curta). O jogador pode seguir ou não.
3. Qualquer lance feito no tabuleiro (por qualquer lado) é detectado pela câmera, validado pelas regras e aplicado.
4. No turno do oponente o sistema apenas observa.

## 3. Arquitetura (nível de contexto)

```
┌──────────────────┐   HTTPS + WebSocket (LAN)   ┌───────────────────────────────┐
│ Telefone/Tablet  │ ──── frames JPEG ─────────▶ │ PC — servidor Python (uv)     │
│ navegador:       │ ◀─── estado, overlay, ───── │  ├─ Visão (OpenCV+MediaPipe)  │
│ câmera + UI      │      sugestões              │  ├─ Motor de regras + Minimax │
└──────────────────┘                             │  ├─ Orquestrador de partida   │
                                                 │  └─ Cliente LLM (openai)      │
                                                 └──────────────┬────────────────┘
                                                                │ HTTP, API OpenAI
                                                                ▼
                                                 ┌───────────────────────────────┐
                                                 │ Hub Gambi  :3000              │
                                                 │ /rooms/<CODE>/v1              │
                                                 └──────┬───────────────┬────────┘
                                                        │ túnel WS      │
                                                  participante A   participante B
                                                  (Ollama, LM Studio, nuvem…)
```

Componentes:

| Componente | Responsabilidade |
|---|---|
| **Cliente web** | Captura a câmera, envia frames, mostra tabuleiro reconhecido, lances e sugestões. HTML/JS simples servido pelo próprio servidor. |
| **Visão** | Localiza o tabuleiro, retifica a perspectiva, classifica cada casa escura (vazia / branca / preta), detecta mão sobre o tabuleiro. |
| **Motor de regras** | Estado do jogo, geração de lances legais, aplicação de lances, promoção, fim de jogo. Puro Python, sem I/O. |
| **Analisador Minimax** | Busca minimax com poda alfa-beta sobre o motor de regras; pontua cada lance legal e devolve a linha principal prevista. Puro Python, sem I/O. |
| **Orquestrador** | Máquina de estados da partida: turnos, modos de jogo, casar observações da câmera com lances legais. |
| **Cliente LLM** | Monta o prompt, chama o Gambi, valida a resposta, aplica retry/fallback. |

### Papel do MediaPipe

O MediaPipe não tem detector pronto de tabuleiro nem de peças de damas. A divisão proposta é:

- **MediaPipe Hand Landmarker** — detecta mão sobre o tabuleiro. Enquanto houver mão (oclusão), a leitura é suspensa; a saída da mão marca o momento de ler o novo estado. É o que torna a detecção de jogadas confiável.
- **OpenCV** — localização do tabuleiro (4 cantos), homografia e recorte das 64 casas.
- **Classificação das casas** — interface plugável com duas implementações:
  1. *Baseline*: heurística de cor/luminância calibrada na posição inicial (sem treino).
  2. *Opcional*: MediaPipe Image Classifier com modelo customizado (vazia/branca/preta), se o baseline não atingir a meta de acurácia.

> Decisão registrada no [ADR 0004](../../docs/adr/0004-visao-mediapipe-maos-opencv-cor-calibrada.md).

## 4. Requisitos funcionais

### 4.1 Captura e conexão (RF-CAP)

- **RF-CAP-01** — O servidor expõe uma página acessível pelo navegador do telefone/tablet na mesma rede local.
- **RF-CAP-02** — A página é servida em **HTTPS** (certificado local/autoassinado), pois navegadores móveis só liberam a câmera em contexto seguro.
- **RF-CAP-03** — A página usa a câmera traseira e envia frames ao servidor por WebSocket (alvo: ≥ 5 fps, até 1280×720, JPEG).
- **RF-CAP-04** — O servidor mostra no terminal a URL de acesso (e um QR code) ao iniciar.
- **RF-CAP-05** — Queda de conexão não perde a partida: ao reconectar, o cliente recebe o estado atual.
- **RF-CAP-06** — Só um dispositivo é a câmera ativa por partida; outros podem conectar como espectadores (somente leitura).

### 4.2 Visão do tabuleiro (RF-VIS)

- **RF-VIS-01** — Calibração: o sistema detecta os 4 cantos do tabuleiro automaticamente e permite ajuste manual tocando/arrastando os cantos na tela.
- **RF-VIS-02** — O sistema retifica a imagem para uma vista de topo e a divide em 8×8 casas.
- **RF-VIS-03** — A orientação (qual lado é das brancas) é definida na calibração e confirmada pelo usuário.
- **RF-VIS-04** — Cada casa escura é classificada como `vazia`, `branca` ou `preta`, com um valor de confiança.
- **RF-VIS-05** — Calibração de cor: com a posição inicial montada, o sistema aprende a aparência de casa vazia, peça branca e peça preta para aquele tabuleiro e iluminação.
- **RF-VIS-06** — Com mão detectada sobre o tabuleiro, a leitura fica suspensa e a UI indica "aguardando".
- **RF-VIS-07** — Uma leitura só é aceita quando estável por N frames consecutivos sem mão (N configurável; padrão 5).
- **RF-VIS-08** — Leituras com confiança abaixo do limiar em qualquer casa são rejeitadas e a UI destaca as casas duvidosas.
- **RF-VIS-09** — Se o tabuleiro ou a câmera se mover (cantos fora de tolerância), o sistema pede recalibração sem encerrar a partida.
- **RF-VIS-10** — **Damas (peças promovidas) não são reconhecidas visualmente**: a promoção é rastreada pelo motor de regras. A câmera só informa ocupação e cor.

### 4.3 Regras e estado (RF-REG)

Variante: **damas brasileiras** (8×8, 12 peças por lado) — ver **Q2**.

- **RF-REG-01** — Peças comuns movem uma casa na diagonal para frente; capturam para frente e para trás.
- **RF-REG-02** — Captura é obrigatória; capturas múltiplas na mesma jogada; vale a **lei da maioria** (obrigatório o lance que captura mais peças).
- **RF-REG-03** — Dama move e captura a qualquer distância na diagonal ("dama voadora").
- **RF-REG-04** — Promoção ao terminar o lance na última fileira (passar por ela no meio de uma captura não promove).
- **RF-REG-05** — Fim de jogo: lado sem peças ou sem lances legais perde; empate por regra de lances sem captura/promoção (20 lances de dama consecutivos) ou por acordo manual.
- **RF-REG-06** — O motor gera a lista completa de lances legais de uma posição e aplica um lance retornando o novo estado.
- **RF-REG-07** — Notação: casas em coordenada algébrica (`a1`–`h8`); lance como `c3-d4` ou `c3xe5xg7`.
- **RF-REG-08** — O histórico de lances é mantido e exportável (JSON e texto).
- **RF-REG-09** — Posição inicial padrão por omissão; é possível iniciar de posição arbitrária editada manualmente na UI (inclusive marcando damas).

### 4.4 Detecção de jogadas (RF-JOG)

- **RF-JOG-01** — A cada leitura aceita, o orquestrador compara a ocupação observada com a ocupação resultante de cada lance legal do lado da vez; se exatamente um lance bate, ele é aplicado.
- **RF-JOG-02** — Se nenhum lance legal bate, o estado não muda e a UI mostra "posição inválida" com as diferenças casa a casa (esperado × visto).
- **RF-JOG-03** — Estado intermediário de captura múltipla (peça movida, capturadas ainda no tabuleiro) não é erro: o sistema aguarda até a posição final ou timeout configurável.
- **RF-JOG-04** — O usuário pode corrigir manualmente: desfazer o último lance ou forçar o estado.
- **RF-JOG-05** — Leitura idêntica ao estado atual é ignorada (ninguém jogou).

### 4.5 Minimax (RF-MMX)

O Minimax tem quatro papéis, conforme o modo:

| Papel | Onde | O que faz |
|---|---|---|
| **Juiz** | Todos os modos | Avalia cada lance jogado (por LLM, Minimax ou humano) e registra pontuação e rótulo. Não interfere na decisão. |
| **Fallback** | Lados controlados por LLM | Fornece o lance quando a LLM falha (RF-LLM-06). |
| **Jogador** | IA × IA | Pode ser escolhido para controlar um lado (ex.: LLM × Minimax como referência de força). |
| **Analista** | Modo assistido | Entrega sua análise à LLM conselheira, que escolhe entre os melhores lances e explica (RF-MOD-07). |

No IA × IA a LLM **não** recebe a análise do Minimax: a disputa entre modelos precisa ser genuína.

- **RF-MMX-01** — Para uma posição, o analisador roda minimax com poda alfa-beta e devolve, **para cada lance legal**: pontuação (do ponto de vista do lado da vez), profundidade alcançada e a linha principal prevista.
- **RF-MMX-02** — Função de avaliação baseada em: material (pedras e damas), avanço das pedras, controle do centro, mobilidade e peças sob ameaça de captura. Vitória/derrota forçada dentro do horizonte é sinalizada ("vence em N", "perde em N").
- **RF-MMX-03** — Aprofundamento iterativo com orçamento de tempo configurável (padrão 1 s) e profundidade máxima configurável (padrão 8 meios-lances); sequências de captura são estendidas além do horizonte para não avaliar no meio de uma troca.
- **RF-MMX-04** — A análise é determinística para a mesma posição e configuração (necessário para testes).
- **RF-MMX-05** — Cada lance recebe um rótulo derivado da diferença para o melhor lance: `melhor`, `bom`, `duvidoso`, `erro`.
- **RF-MMX-06** — Juiz: todo lance jogado é avaliado e gravado no histórico com pontuação e rótulo; ao fim da partida há um resumo por lado (quantidade de cada rótulo, perda média de pontuação).
- **RF-MMX-07** — Jogador: joga sempre o lance de maior pontuação; a força é ajustável pela profundidade máxima.

### 4.6 Integração com LLM via Gambi (RF-LLM)

Fatos da documentação do Gambi que fundamentam esta seção: o hub expõe API compatível com OpenAI em `http://<host>:3000/rooms/<CODE>/v1`; não há SDK Python oficial (usa-se o cliente `openai`); o campo `model` aceita `*`/`any`, `model:<nome>` ou `<participant-id>`; o hub não tem autenticação; tool calling, saída estruturada e visão **não são documentados**.

- **RF-LLM-01** — URL do hub e código da sala são configuráveis (variáveis de ambiente / `.env` / UI).
- **RF-LLM-02** — O sistema lista os participantes disponíveis (`GET /v1/models`) e permite escolher um por lado.
- **RF-LLM-03** — A LLM recebe: regras resumidas, cor da vez, tabuleiro em texto, últimos lances e a **lista numerada de lances legais**. Ela responde com o **número** do lance escolhido e uma justificativa curta.
- **RF-LLM-03a** — Só no modo assistido, cada lance da lista vai acompanhado da análise Minimax (pontuação, rótulo, linha principal) e a justificativa deve se apoiar nela. No IA × IA a análise não é enviada.
- **RF-LLM-04** — A resposta é extraída de texto livre (sem depender de tool calling nem de JSON mode). A LLM nunca recebe imagem.
- **RF-LLM-05** — Resposta inválida (sem número, fora da lista) gera nova tentativa com mensagem corretiva, até K vezes (padrão 2).
- **RF-LLM-06** — Esgotadas as tentativas, ou em erro/timeout do hub (404, 409 ocupado, 502, 503), aplica-se o **fallback**: o melhor lance segundo o Minimax. A UI marca o lance como "fallback".
- **RF-LLM-07** — Se há apenas um lance legal, ele é jogado sem chamar a LLM.
- **RF-LLM-08** — Timeout por chamada configurável (padrão 60 s, pensando em modelos locais lentos).
- **RF-LLM-09** — Usa a Responses API (preferida pelo Gambi) com fallback para Chat Completions.
- **RF-LLM-10** — Cada chamada é registrada: participante, prompt, resposta bruta, lance, latência, tentativas.

### 4.7 Modos de jogo (RF-MOD)

**IA × IA**

- **RF-MOD-01** — Cada lado é controlado por uma **LLM** (seletor de modelo do Gambi, idealmente participantes diferentes) ou pelo **Minimax** (RF-MMX-07). Combinações válidas: LLM × LLM, LLM × Minimax, Minimax × Minimax.
- **RF-MOD-01a** — A UI mostra, a cada lance, o rótulo do juiz Minimax e, ao final, o resumo de qualidade por lado (RF-MMX-06).
- **RF-MOD-02** — O lance da IA é exibido na tela (casas destacadas, peças a remover) e fica **pendente** até a câmera confirmar que o tabuleiro físico o reflete.
- **RF-MOD-03** — Se o operador executa algo diferente do lance pendente, a UI mostra a divergência e não avança.
- **RF-MOD-04** — Controles: pausar, retomar, encerrar, velocidade (pedir o próximo lance automaticamente ou sob comando).
- **RF-MOD-05** — **Modo simulado** (sem câmera): os lances da IA são aplicados direto no estado. Serve para testar a integração com o Gambi e para demonstração.

**Jogador assistido × Humano**

- **RF-MOD-06** — O jogador assistido escolhe cor e modelo conselheiro.
- **RF-MOD-07** — No turno do assistido, o Minimax analisa a posição e a LLM conselheira recebe essa análise (RF-LLM-03a), escolhe o lance e explica em linguagem natural. A sugestão é exibida com a justificativa e a pontuação Minimax; é possível pedir outra sugestão.
- **RF-MOD-07a** — Enquanto a LLM não responde, a UI já mostra o melhor lance do Minimax como sugestão provisória.
- **RF-MOD-07b** — Depois de cada lance do assistido, a UI mostra o rótulo do juiz para o lance efetivamente jogado.
- **RF-MOD-08** — A sugestão é conselho: qualquer lance legal executado no tabuleiro é aceito.
- **RF-MOD-09** — No turno do oponente nenhuma sugestão é exibida.
- **RF-MOD-10** — Opção de ocultar a sugestão até o jogador pedir (para não ficar visível ao oponente).

### 4.8 Interface (RF-UI)

- **RF-UI-01** — Tela do telefone: vídeo com contorno do tabuleiro sobreposto, tabuleiro digital reconhecido, lado da vez, lance pendente/sugestão, alertas.
- **RF-UI-02** — Fluxo de preparação guiado: conectar → calibrar cantos → confirmar orientação → calibrar cores → escolher modo e modelos → iniciar.
- **RF-UI-03** — Indicador de saúde: fps recebido, status do hub Gambi, participantes online.
- **RF-UI-04** — Mesma interface utilizável no navegador do PC (espectador ou modo simulado).
- **RF-UI-05** — Idioma da interface: português (pt-BR).

## 5. Requisitos não funcionais

| ID | Requisito |
|---|---|
| **RNF-01** | Acurácia de classificação por casa ≥ 99% em iluminação interna normal, após calibração; estado completo do tabuleiro correto em ≥ 95% das leituras aceitas. |
| **RNF-02** | Tempo entre a mão sair do tabuleiro e o lance ser reconhecido ≤ 2 s. |
| **RNF-03** | Processamento de visão ≥ 5 fps em CPU de notebook comum, sem GPU. |
| **RNF-04** | Funciona 100% em rede local, sem internet (desde que os modelos do Gambi sejam locais). |
| **RNF-05** | Nenhum frame é gravado em disco por padrão; gravação só com flag de depuração explícita. |
| **RNF-06** | O servidor escuta apenas na LAN e não deve ser exposto à internet (nem ele nem o hub Gambi têm autenticação). |
| **RNF-07** | Motor de regras com cobertura de testes ≥ 90%, incluindo lei da maioria, dama voadora e promoção. |
| **RNF-10** | O Minimax respeita o orçamento de tempo (RF-MMX-03) e roda fora do laço de visão, sem derrubar o fps de RNF-03. Testado com posições táticas de resposta conhecida. |
| **RNF-08** | Pipeline de visão testável offline com imagens/vídeos gravados (fixtures), sem câmera. |
| **RNF-09** | Windows 11 como plataforma principal do servidor; não usar nada exclusivo de Windows. Cliente: Chrome Android e Safari iOS atuais. |

## 6. Restrições técnicas

- **Linguagem e ferramentas**: Python gerenciado com **uv** (`pyproject.toml`, `uv.lock`, `uv run`). Versão do Python limitada pelo suporte do pacote `mediapipe`.
- **Bibliotecas previstas**: `mediapipe`, `opencv-python`, `numpy`, `fastapi` + `uvicorn` (HTTP/WebSocket), `openai` (cliente do Gambi), `pydantic-settings`, `pytest`, `ruff`.
- **Gambi**: instalado à parte (`gambi hub serve`, `gambi room create`, `gambi participant join`). Este projeto é só **cliente** do hub; não gerencia hub, sala nem participantes.
- **Front-end**: HTML/CSS/JS sem etapa de build.

## 7. Modelo de dados (conceitual)

- **Cor**: `branca` | `preta`.
- **Peça**: cor + tipo (`pedra` | `dama`).
- **Tabuleiro**: 32 casas escuras → peça ou vazio.
- **Observação**: 32 casas → `vazia` | `branca` | `preta` + confiança, com timestamp.
- **Lance**: origem, sequência de destinos, casas capturadas, promoção (sim/não).
- **AnáliseMinimax**: por lance legal — pontuação, rótulo, profundidade, linha principal.
- **Partida**: modo, configuração dos lados (humano / LLM + seletor de modelo / Minimax + profundidade), tabuleiro, lado da vez, histórico, status (`preparando`, `em_jogo`, `aguardando_execução`, `posição_inválida`, `pausada`, `encerrada`), resultado.
- **RegistroLLM**: ver RF-LLM-10.

## 8. Critérios de aceitação

- **CA-01** — Dado o tabuleiro na posição inicial e a calibração feita, o tabuleiro digital mostra as 24 peças nas casas e cores corretas.
- **CA-02** — Ao mover fisicamente uma peça num lance legal simples, o lance aparece no histórico em até 2 s após a mão sair.
- **CA-03** — Uma captura dupla executada peça a peça é registrada como um único lance `axbxc`, sem alerta de erro durante a execução.
- **CA-04** — Mover uma peça para uma casa ilegal gera "posição inválida", indica a casa errada e não altera o estado; desfazer o movimento físico limpa o alerta.
- **CA-05** — Uma pedra que chega à última fileira passa a ser tratada como dama nos lances seguintes, sem intervenção visual.
- **CA-06** — Havendo captura disponível, a lista enviada à LLM contém apenas capturas, e apenas as de maior número de peças.
- **CA-07** — Em IA × IA simulado com dois participantes Gambi online, uma partida completa roda até o fim sem intervenção, com log de todas as chamadas.
- **CA-08** — Em IA × IA com câmera, o turno só avança depois que o tabuleiro físico reflete o lance anunciado.
- **CA-09** — No modo assistido, a sugestão aparece só no turno do jogador assistido, e um lance diferente da sugestão é aceito normalmente.
- **CA-10** — Com o hub Gambi fora do ar, a partida continua usando o fallback e a UI indica o problema.
- **CA-11** — A LLM respondendo texto inútil duas vezes seguidas resulta em lance de fallback marcado como tal, nunca em lance ilegal.
- **CA-13** — Numa posição com captura que ganha peça sem compensação, o Minimax rotula esse lance como `melhor`; numa posição em que um lance entrega uma peça de graça, ele é rotulado `erro`.
- **CA-14** — Uma partida LLM × Minimax simulada roda até o fim, e o resumo final mostra a contagem de rótulos de cada lado.
- **CA-15** — No IA × IA, o prompt registrado da LLM não contém pontuações do Minimax; no modo assistido, contém.
- **CA-16** — No modo assistido, a sugestão provisória do Minimax aparece em até 2 s, antes da resposta da LLM.
- **CA-12** — Fechar e reabrir a página no telefone durante a partida restaura o estado sem perder o histórico.

## 9. Questões levantadas e resolução

Todas foram resolvidas com a proposta da tabela (2026-11-10). As que viraram decisão de arquitetura têm ADR em [docs/adr/](../../docs/adr/README.md): Q1 e Q4 → ADR 0004; Q2 → ADR 0006; Q6 → ADR 0003; Q7 → ADR 0007.

| # | Questão | Resolução |
|---|---|---|
| **Q1** | Papel do MediaPipe: Hand Landmarker + OpenCV + heurística de cor, ou modelo MediaPipe customizado para peças desde a v1? | Começar pelo primeiro; modelo customizado só se RNF-01 não for atingido. |
| **Q2** | Variante das regras: damas brasileiras (lei da maioria, dama voadora)? | Sim. |
| **Q3** | Em IA × IA, o tabuleiro físico é obrigatório ou o modo simulado basta em parte dos usos? | Ambos (RF-MOD-02 e RF-MOD-05). |
| **Q4** | Posição da câmera: suporte fixo acima do tabuleiro ou na mão/ângulo livre? | Suporte fixo, ângulo até ~45°; câmera na mão não é suportada na v1. |
| **Q5** | Cores reais das peças e casas (ex.: peças vermelhas/pretas, casas verdes)? | A calibração de cor (RF-VIS-05) torna isso independente, desde que as duas cores de peça sejam distinguíveis entre si e do fundo. |
| **Q6** | HTTPS local: certificado autoassinado (aviso no navegador) ou `mkcert`? | Autoassinado gerado na primeira execução; documentar `mkcert` como alternativa. |
| **Q7** | Modelos pequenos locais erram muito mesmo escolhendo de uma lista. Aceita-se fallback frequente ou exige-se modelo mínimo? | Aceitar e exibir a taxa de fallback e o resumo do juiz Minimax por modelo. |
| **Q8** | Sugestão no modo assistido: mostrar no mesmo telefone que filma (visível ao oponente) ou em segundo dispositivo? | Segundo dispositivo opcional como "tela do jogador" (aproveita RF-CAP-06); RF-MOD-10 cobre o caso de um só aparelho. |

## 10. Riscos

| Risco | Mitigação |
|---|---|
| Iluminação/sombras degradam a classificação de cor. | Calibração por sessão, limiar de confiança, classificador plugável (Q1). |
| Peça escura sobre casa escura tem pouco contraste. | Usar mais de uma característica (luminância, saturação, borda circular); modelo customizado como plano B. |
| Recursos não documentados do Gambi (tool calling, JSON mode, streaming). | Não depender deles: escolha por índice em texto livre (RF-LLM-03/04). |
| Participante Gambi ocupado (409) ou caiu (503) no meio da partida. | Retry curto + fallback (RF-LLM-06); status visível (RF-UI-03). |
| Câmera do navegador bloqueada sem HTTPS. | RF-CAP-02. |
| Suporte do `mediapipe` a versões novas de Python/Windows. | Fixar a versão do Python no `pyproject.toml` conforme o pacote. |

## 11. Marcos sugeridos

1. **M1 — Motor de regras e Minimax** com testes (sem câmera, sem LLM) (CA-13).
2. **M2 — Gambi + modo IA × IA simulado** (CA-06, CA-07, CA-10, CA-11, CA-14, CA-15).
3. **M3 — Captura e visão**: página HTTPS, streaming, calibração, classificação (CA-01).
4. **M4 — Detecção de jogadas** com gating por mão (CA-02 a CA-05).
5. **M5 — Modos completos com câmera**: IA × IA físico e assistido (CA-08, CA-09, CA-12).
