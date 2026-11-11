# tasks.md — Dama IA Gambi

> Tarefas (SDD) — versão 0.1, 2026-11-10. Deriva de [spec.md](spec.md) e [plan.md](plan.md).

Convenções:

- IDs `T<marco><número>`. Marque `[x]` ao concluir.
- Onde uma tarefa diz "anotar no plano", uma descoberta que mude uma decisão vira um novo ADR em `docs/adr/`.
- **Dep.** = tarefas que precisam estar prontas antes. **[P]** = pode ser feita em paralelo com as vizinhas marcadas [P].
- Cada tarefa termina com `uv run pytest` e `uv run ruff check` passando.
- "Pronto quando" é o teste de aceitação da tarefa.

## M0 — Esqueleto

- [x] **T001 — Criar o projeto uv**
  `uv init --package` com nome `dama`, Python `>=3.12,<3.13`, `git init`, `.gitignore` (`.venv`, `dados/`, `modelos/`, `.env`).
  Pronto quando: `uv run python -c "import dama"` funciona.
- [x] **T002 — Dependências** · Dep. T001
  `uv add` das bibliotecas da seção 2 do plano; grupo `dev` com pytest, pytest-asyncio, pytest-cov, ruff, httpx.
  Pronto quando: `uv sync` conclui e `uv run python -c "import mediapipe, cv2, fastapi, openai"` funciona.
- [x] **T003 — Estrutura de pastas e ferramentas** · Dep. T002
  Pacotes vazios `regras`, `minimax`, `visao`, `llm`, `jogo`, `web`; configuração de ruff e pytest no `pyproject.toml`; um teste trivial.
  Pronto quando: `uv run pytest` e `uv run ruff check` passam.
- [x] **T004 — Configuração e CLI mínima** · Dep. T003
  `config.py` (Settings com prefixo `DAMA_`), `.env.example`, `cli.py` com typer e entrada `dama` no `pyproject.toml`.
  Pronto quando: `uv run dama --help` lista os comandos (ainda vazios).

## M1 — Regras e Minimax

- [x] **T101 — Tipos e tabuleiro** · Dep. T003
  `tipos.py`, `tabuleiro.py`: 32 casas, tupla imutável, posição inicial, conversão índice ↔ `a1`–`h8`, impressão em texto 8×8, tabela de raios diagonais.
  Pronto quando: testes de ida e volta da notação e da posição inicial (12 + 12 peças, `a1` escura e branca).
- [x] **T102 — Lances simples** · Dep. T101
  Pedra anda uma casa para frente; dama anda a distância.
  Pronto quando: contagem de lances da posição inicial = 7 para cada lado; testes de dama em tabuleiro vazio.
- [x] **T103 — Capturas** · Dep. T102
  Pedra captura nas 4 direções; dama captura a distância e pousa em qualquer casa livre atrás; capturas múltiplas; peça não pode ser saltada duas vezes e só sai ao fim do lance.
  Pronto quando: testes com posições montadas para cada caso, incluindo captura em volta e a regra da peça "fantasma".
- [x] **T104 — Captura obrigatória e lei da maioria** · Dep. T103
  Pronto quando: posição com capturas de 1, 2 e 3 peças devolve só as de 3 (CA-06).
- [x] **T105 — Aplicar lance, promoção e notação de lance** · Dep. T103
  Promoção só se terminar na última fileira; `c3-d4` e `c3xe5xg7` com ida e volta.
  Pronto quando: teste de pedra que passa pela última fileira no meio da captura e não promove (RF-REG-04).
- [x] **T106 — Partida: histórico e fim de jogo** · Dep. T104, T105
  Sem peças, sem lances, empate por 20 lances de dama; desfazer último lance; exportar JSON e texto.
  Pronto quando: testes de cada condição de fim e de exportar/reimportar.
- [x] **T107 — Perft e cobertura** · Dep. T106
  Contagem de nós em profundidades 1–5 a partir da posição inicial, travada em teste; cobertura de `regras/` ≥ 90% (RNF-07).
  Pronto quando: `uv run pytest --cov=dama.regras` ≥ 90%.
- [x] **T108 — Função de avaliação** [P] · Dep. T106
  Material, avanço, centro, mobilidade, peça ameaçada (RF-MMX-02).
  Pronto quando: testes de simetria (posição espelhada tem pontuação oposta) e de material.
- [x] **T109 — Busca negamax alfa-beta** · Dep. T108
  Aprofundamento iterativo, limite de tempo e de profundidade, quiescência em capturas, ordenação de lances, determinismo.
  Pronto quando: acha vitória forçada em 2 e em 3 lances em posições de teste; mesma posição dá o mesmo resultado em duas execuções.
- [x] **T110 — Análise por lance, rótulos e resumo do juiz** · Dep. T109
  `AnaliseMinimax` para todos os lances legais, rótulos `melhor/bom/duvidoso/erro`, resumo por lado (RF-MMX-01/05/06).
  Pronto quando: CA-13 passa.
- [x] **T111 — Benchmark do Minimax** · Dep. T109
  Medir profundidade alcançada em 1 s em posições de abertura, meio e final. Se < 8, aplicar tabela de transposição; registrar no plano o padrão escolhido.
  Pronto quando: número medido e padrão de profundidade definidos em `config.py`.

## M2 — Gambi e modo simulado

- [x] **T201 — Servidor falso compatível com OpenAI** · Dep. T003
  Fixture de teste (FastAPI) com `/v1/models`, `/v1/responses`, `/v1/chat/completions` e respostas roteirizadas: válida, lixo, 409, 503, lenta, sem Responses API.
  Pronto quando: a fixture sobe e responde nos testes.
- [x] **T202 — Cliente Gambi** · Dep. T201, T004
  `AsyncOpenAI` com base URL da sala; listar participantes; Responses com fallback para Chat Completions; timeout.
  Pronto quando: testes contra o servidor falso para os dois protocolos.
- [x] **T203 — Prompt** [P] · Dep. T106, T110
  Montagem com e sem análise Minimax (RF-LLM-03/03a); teste de snapshot do texto.
  Pronto quando: CA-15 coberto por teste (sem pontuações no IA × IA, com no assistido).
- [x] **T204 — Parser da resposta** [P] · Dep. T105
  `LANCE: n`, notação algébrica, número isolado; tudo o mais inválido.
  Pronto quando: tabela de ~20 textos de exemplo com o resultado esperado.
- [x] **T205 — Jogador LLM** · Dep. T202, T203, T204
  Retry com mensagem corretiva, espera em 409, fallback para o Minimax, atalho de lance único, `RegistroLLM`.
  Pronto quando: CA-10 e CA-11 passam contra o servidor falso.
- [x] **T206 — Controladores** · Dep. T205
  `ControladorLLM`, `ControladorMinimax`, `ControladorHumano` com a mesma interface.
  Pronto quando: testes unitários de cada um.
- [x] **T207 — Orquestrador (sem câmera)** · Dep. T206
  Máquina de estados, laço de turno, juiz a cada lance, eventos, pausar/retomar/encerrar.
  Pronto quando: partida Minimax × Minimax roda até o fim em teste, com rótulos no histórico.
- [x] **T208 — Persistência** · Dep. T207
  Salvar a cada lance em `dados/partidas/`, recarregar, exportar.
  Pronto quando: teste de salvar no meio, recarregar e continuar.
- [x] **T209 — Comandos `dama simular` e `dama checar-gambi`** · Dep. T207
  `simular`: escolhe os lados (LLM/Minimax), imprime tabuleiro e lances no terminal. `checar-gambi`: testa hub, sala, participantes e qual protocolo funciona.
  Pronto quando: CA-14 passa em teste (LLM falsa × Minimax).
- [x] **T210 — Validação com Gambi real** (manual) · Dep. T209
  Hub no ar, sala criada, ao menos um participante. Rodar `checar-gambi` e uma partida LLM × Minimax e uma LLM × LLM.
  Pronto quando: CA-07 verificado; anotar no plano o que o hub real aceitou (Responses ou Chat) e a taxa de fallback observada.

## M3 — Captura e visão

- [ ] **T301 — Spike: câmera do telefone via HTTPS local** · Dep. T004
  Página mínima com `getUserMedia` servida com certificado autoassinado; testar no Chrome Android e no Safari iOS, incluindo WebSocket seguro.
  Pronto quando: resultado anotado no plano (funciona com autoassinado ou precisa de `mkcert`).
  Situação em 2026-11-11: código pronto e testado no PC com um cliente WSS. Falta abrir no telefone e anotar se o certificado autoassinado basta.
- [x] **T302 — Spike: Hand Landmarker no mediapipe 1.x** [P] · Dep. T002
  Script que carrega o modelo `.task` e detecta mão numa foto e num vídeo curto.
  Pronto quando: API confirmada e anotada no plano; script de download do modelo para `modelos/`.
  Situação em 2026-11-11: `visao/mao.py` e `dama baixar-modelo` escritos com a API do mediapipe 1.2.2 (`HandLandmarker` em modo vídeo). Modelo baixado para `modelos/`: carrega em 4 s, leva 19 ms por frame e não dispara nas fotos do tabuleiro nem na cena com as 24 peças. Falta o caso positivo, com uma mão de verdade sobre o tabuleiro.
- [ ] **T303 — TLS e inicialização do servidor** · Dep. T301
  `tls.py` (certificado com IPs locais), `dama serve` sobe uvicorn em 8443, imprime URL e QR code (RF-CAP-02/04).
  Pronto quando: a página abre no telefone.
  Situação em 2026-11-11: `dama serve` sobe em HTTPS e mostra endereço e QR code; conferido no PC. Falta abrir no telefone.
- [x] **T304 — Protocolo WebSocket** · Dep. T303
  `protocolo.py` (modelos das mensagens), `/ws` com papéis `camera`/`jogador`/`espectador`, uma câmera por partida (RF-CAP-06).
  Pronto quando: testes com cliente WebSocket de teste.
  Situação em 2026-11-11: 13 testes em `tests/web/`.
- [ ] **T305 — Cliente: câmera e envio de frames** · Dep. T304
  `index.html`/`app.js`: câmera traseira, JPEG a 5 fps com contrapressão, indicador de fps (RF-CAP-03, RF-UI-03).
  Pronto quando: o servidor registra ≥ 5 fps recebidos do telefone.
  Situação em 2026-11-11: página pronta; um cliente simulado no PC enviou a 5 fps e o servidor contou 4,7 recebidos, sem descartar nenhum. Falta medir com o telefone.
- [x] **T306 — Localização do tabuleiro** [P] · Dep. T002
  Máscara de saturação + envoltória convexa + quadrilátero; encolhimento para a área de jogo; homografia para 640×640.
  Pronto quando: nas duas fotos de `tests/fixtures/tabuleiro/`, os cantos ficam dentro de uma tolerância dos cantos anotados à mão.
  Situação em 2026-11-11: acerta a grade nas duas fotos reais e na cena sintética, com e sem peças.
- [ ] **T307 — Calibração de cantos na tela** · Dep. T305, T306
  Sobreposição com os 4 cantos detectados, arrastáveis; mensagem `cantos`; visualização do tabuleiro retificado (RF-VIS-01).
  Pronto quando: ajuste manual no telefone alinha a grade com as casas.
  Situação em 2026-11-11: cantos arrastáveis e prévia retificada com grade implementados. Falta conferir o toque no telefone.
- [x] **T308 — Orientação** · Dep. T306
  Detectar os dois cantos escuros, restringir a 2 orientações, perguntar o lado das brancas (RF-VIS-03).
  Pronto quando: teste nas fixtures acha os cantos escuros corretos.
  Situação em 2026-11-11: testado nas duas fotos reais.
- [ ] **T309 — Coleta de fixtures com peças** (manual) · Dep. T305
  Modo `GRAVAR_FRAMES`; fotografar posição inicial e ~10 posições variadas, em 2 condições de luz, anotando o estado esperado em JSON.
  Pronto quando: fixtures e anotações em `tests/fixtures/`.
  Situação em 2026-11-11: botão "Salvar foto" e modo `DAMA_GRAVAR_FRAMES` prontos. Falta fotografar o tabuleiro com as peças.
- [ ] **T310 — Classificador de cor** · Dep. T306, T309
  Interface `Classificador`; `ClassificadorCor` com disco central, mediana, descarte de pixels estourados, características de luminância e saturação, 3 centroides, confiança por margem.
  Pronto quando: acurácia por casa ≥ 99% nas fixtures (RNF-01); número registrado.
  Situação em 2026-11-11: classificador pronto; 100% das casas em 72 cenas sintéticas. Falta medir nas fotos reais (T309).
- [ ] **T311 — Calibração de cor na posição inicial** · Dep. T310, T308
  Mensagem `calibrar_cores`; aprende os centroides das 12 + 12 + 8 casas; atualização lenta após cada lance aceito (RF-VIS-05).
  Pronto quando: CA-01 verificado com o tabuleiro real.
  Situação em 2026-11-11: calibração e atualização lenta prontas; CA-01 passa na cena sintética. Falta verificar com o tabuleiro real.
- [ ] **T312 — Pipeline em thread e tabuleiro digital ao vivo** · Dep. T311
  Thread com fila de tamanho 1; mensagem `visao`; grade do tabuleiro reconhecido na página, com casas duvidosas destacadas (RF-VIS-08, RF-UI-01).
  Pronto quando: mover uma peça atualiza o tabuleiro digital; processamento ≥ 5 fps (RNF-03).
  Situação em 2026-11-11: thread com fila de tamanho 1 e tabuleiro digital prontos; 46 ms por frame no PC. Falta ver uma peça real se mover.

## M3b — Jogo pela tela (sem câmera)

Decidido em 2026-11-11: a calibração pela câmera falhou em seis tentativas seguidas com o tabuleiro real (fundos e luzes diferentes). A câmera fica de lado por enquanto e a partida passa a ser jogada por toque (RF-UI-06).

- [x] **T320** Mesa de jogo no servidor (`web/mesa.py`)
  Nova partida com cada lado humano, Minimax ou LLM; lance por toque validado pelo motor; IAs jogam sozinhas; dica e desfazer.
  Pronto quando: testes pelo WebSocket cobrem partida humano × Minimax, lance ilegal, espectador, dica e desfazer.
- [x] **T321** Tabuleiro jogável na página
  Tocar na peça mostra os destinos; capturas em sequência são seguidas casa a casa; lista de lances com o rótulo do juiz.
  Pronto quando: uma partida humano × Minimax é jogada no navegador do PC.
- [ ] **T322** Conferir no telefone
  Pronto quando: uma partida inteira é jogada por toque no telefone, e outra contra uma LLM do Gambi.

## M4 — Detecção de jogadas

- [ ] **T401 — Detecção de mão** · Dep. T302, T312
  `mao.py`: mão dentro do polígono dilatado suspende a leitura; UI mostra "aguardando" (RF-VIS-06).
  Pronto quando: teste com vídeo gravado de uma jogada: nenhuma observação emitida enquanto há mão.
- [ ] **T402 — Estabilidade** · Dep. T401
  N frames iguais sem mão e com confiança mínima antes de emitir `Observacao` (RF-VIS-07).
  Pronto quando: teste com sequência sintética de leituras.
- [ ] **T403 — Casamento observação → lance** [P] · Dep. T106
  Dicionário ocupação → lance, estado `intermediario`, timeout, diferenças casa a casa, lance pendente esperado (RF-JOG-01 a 05).
  Pronto quando: CA-03 e CA-04 passam com observações sintéticas.
- [ ] **T404 — Integração câmera → orquestrador** · Dep. T402, T403, T207
  Observações alimentam o orquestrador; `ControladorHumano` recebe o lance casado.
  Pronto quando: CA-02 e CA-05 verificados com o tabuleiro real.
- [ ] **T405 — Alertas e correção manual** · Dep. T404
  UI de "posição inválida" com casas divergentes; desfazer; forçar estado/editar posição, inclusive damas (RF-JOG-04, RF-REG-09).
  Pronto quando: lance ilegal mostra o alerta e desfazer o movimento físico o limpa.
- [ ] **T406 — Deriva e recalibração** · Dep. T404
  Verificação periódica dos cantos; estado `recalibrar` sem perder a partida (RF-VIS-09).
  Pronto quando: empurrar o tabuleiro durante a partida pede recalibração e o jogo continua depois.

## M5 — Modos completos com câmera

- [ ] **T501 — Fluxo de preparação e criação de partida** · Dep. T405
  Passo a passo na UI: conectar → cantos → orientação → cores → modo e lados (LLM/Minimax/humano, participantes do Gambi) → iniciar (RF-UI-02, RF-LLM-02).
  Pronto quando: é possível criar os dois modos pelo telefone.
- [ ] **T502 — IA × IA físico** · Dep. T501
  Lance pendente destacado, confirmação pela câmera, divergência, controles de pausa e ritmo, rótulo do juiz por lance e resumo final (RF-MOD-01 a 04).
  Pronto quando: CA-08 verificado.
- [ ] **T503 — Modo assistido** · Dep. T501
  Sugestão provisória do Minimax, sugestão da LLM com análise, pedir outra, ocultar até pedir, rótulo do lance jogado (RF-MOD-06 a 10).
  Pronto quando: CA-09 e CA-16 verificados.
- [ ] **T504 — Tela do jogador e espectadores** · Dep. T503
  Segundo dispositivo no papel `jogador` vê sugestões; `espectador` não vê; mesma UI no navegador do PC (RF-UI-04).
  Pronto quando: dois aparelhos conectados mostram conteúdos diferentes conforme o papel.
- [ ] **T505 — Reconexão e retomada** · Dep. T502
  Reabrir a página restaura estado e calibração; reiniciar o servidor recarrega a partida salva (RF-CAP-05).
  Pronto quando: CA-12 verificado.
- [ ] **T506 — Modo simulado na UI** [P] · Dep. T501
  IA × IA sem câmera pelo navegador (RF-MOD-05).
  Pronto quando: partida completa assistida pelo PC.
- [ ] **T507 — README e roteiro de teste manual** · Dep. T505
  Instalação, pré-requisitos do Gambi, firewall, aviso do certificado, dicas de luz e fixação do tabuleiro; roteiro que percorre CA-01 a CA-16.
  Pronto quando: seguir o README numa máquina limpa leva a uma partida jogada.

## Caminho crítico

`T001 → T101 → T103 → T106 → T109 → T110 → T205 → T207` (jogo completo no terminal), depois `T303 → T305 → T306 → T310 → T312 → T402 → T404 → T502/T503`.

Dependem de você, fora do código: **T210** (Gambi no ar), **T301** (testar no seu telefone), **T309** (fotos com as peças) e as verificações com o tabuleiro real em M3–M5.
