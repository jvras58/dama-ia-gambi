# plan.md — Dama IA Gambi

> Plano técnico (SDD) — versão 0.1, 2026-11-10. Descreve **como** implementar a [spec.md](spec.md). A quebra em tarefas fica para `tasks.md`.

## 1. Decisões assumidas

As decisões de arquitetura deste plano estão registradas em [docs/adr/](../../docs/adr/README.md) (ADRs 0002 a 0008). As questões da spec (seção 9) foram fechadas assim:

| # | Decisão |
|---|---|
| Q1 | MediaPipe Hand Landmarker + OpenCV + heurística de cor calibrada. Classificador plugável; modelo customizado só se RNF-01 falhar. |
| Q2 | Damas brasileiras. |
| Q3 | IA × IA com tabuleiro físico **e** modo simulado. |
| Q4 | Câmera em suporte fixo, ângulo até ~45°. |
| Q5 | Cores aprendidas na calibração; nada fixo no código. |
| Q6 | Certificado autoassinado gerado na primeira execução; `mkcert` documentado como alternativa. |
| Q7 | Fallback frequente é aceito; taxa de fallback e resumo do juiz são exibidos por modelo. |
| Q8 | Segundo dispositivo opcional como "tela do jogador"; opção de ocultar sugestão para um só aparelho. |

## 2. Stack

Verificado nesta máquina em 2026-11-10: `uv 0.11.8`; Python 3.10–3.14 disponíveis via uv; `mediapipe 1.2.2` no PyPI com wheel `py3-none-win_amd64`.

| Item | Escolha | Motivo |
|---|---|---|
| Python | **3.12** (`requires-python = ">=3.12,<3.13"`) | Versão madura com wheels de todas as dependências; fixar evita surpresas com mediapipe/opencv. |
| Gerenciador | `uv` (`uv init --package`, `uv add`, `uv run`) | Requisito. |
| Servidor | `fastapi` + `uvicorn[standard]` | HTTP, WebSocket e TLS no mesmo processo. |
| Visão | `mediapipe`, `opencv-python-headless`, `numpy` | Headless: não há janela no servidor. |
| LLM | `openai` (cliente assíncrono) | Caminho documentado pelo Gambi para Python. |
| Config | `pydantic-settings` | `.env` + variáveis de ambiente com prefixo `DAMA_`. |
| TLS | `cryptography` | Gerar o certificado autoassinado. |
| QR | `qrcode` | URL de acesso no terminal (RF-CAP-04). |
| CLI | `typer` | `dama serve`, `dama simular`, `dama checar-gambi`. |
| Dev | `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `httpx` | Testes e lint. |
| Front-end | HTML/CSS/JS puro em `static/` | Sem etapa de build (restrição da spec). |

> **Ponto a confirmar no início do M3**: a API do `mediapipe` 1.x para o Hand Landmarker (Tasks API, modo vídeo, arquivo `.task` do modelo). Este plano assume a Tasks API; um spike de meia hora confirma antes de escrever o módulo.

## 3. Estrutura do projeto

```
dama-ia-gambi/
├── pyproject.toml
├── uv.lock
├── .env.example
├── README.md
├── docs/                      # constituicao.md, adr/
├── specs/001-dama-ia-gambi/   # spec.md, plan.md, tasks.md
├── src/dama/
│   ├── __init__.py
│   ├── cli.py                 # typer: serve, simular, checar-gambi
│   ├── config.py              # Settings (pydantic-settings)
│   ├── regras/                # puro, sem I/O
│   │   ├── tipos.py           # Cor, Peca, Lance, Tabuleiro
│   │   ├── tabuleiro.py       # representação, notação, posição inicial
│   │   ├── gerador.py         # lances legais (lei da maioria, dama voadora)
│   │   └── partida.py         # aplicar lance, promoção, fim de jogo, histórico
│   ├── minimax/               # puro, sem I/O
│   │   ├── avaliacao.py       # função de avaliação
│   │   ├── busca.py           # negamax alfa-beta, aprof. iterativo, quiescência
│   │   └── analise.py         # AnaliseMinimax por lance, rótulos, resumo do juiz
│   ├── visao/
│   │   ├── localizacao.py     # cantos automáticos, homografia, recorte das casas
│   │   ├── classificador.py   # Protocol + ClassificadorCor (baseline)
│   │   ├── mao.py             # MediaPipe Hand Landmarker
│   │   ├── estabilidade.py    # N frames estáveis, deriva dos cantos
│   │   └── pipeline.py        # frame -> Observacao | estado ("mao", "instavel", ...)
│   ├── llm/
│   │   ├── cliente.py         # AsyncOpenAI apontado para o Gambi; listar participantes
│   │   ├── prompt.py          # montagem do prompt (com/sem análise Minimax)
│   │   ├── parser.py          # extrair o número do lance do texto livre
│   │   └── jogador.py         # retry, timeout, fallback, RegistroLLM
│   ├── jogo/
│   │   ├── casamento.py       # Observacao -> lance legal (RF-JOG)
│   │   ├── orquestrador.py    # máquina de estados da partida
│   │   ├── controladores.py   # ControladorLLM, ControladorMinimax, ControladorHumano
│   │   └── persistencia.py    # salvar/exportar partida (JSON, texto)
│   └── web/
│       ├── app.py             # FastAPI: rotas, WebSocket, estáticos
│       ├── tls.py             # certificado autoassinado
│       ├── protocolo.py       # modelos pydantic das mensagens WS
│       └── static/            # index.html, app.js, estilo.css
├── modelos/                   # hand_landmarker.task (baixado no setup, fora do git)
├── dados/                     # partidas salvas, certificado (fora do git)
└── tests/
    ├── regras/  minimax/  llm/  jogo/  visao/  web/
    └── fixtures/              # posições, imagens e vídeos gravados
```

Regra de dependência: `regras` não importa nada do projeto; `minimax` importa só `regras`; `visao` e `llm` não se conhecem; `jogo` junta tudo; `web` só fala com `jogo`.

## 4. Projeto por módulo

### 4.1 Regras

- **Representação**: 32 casas escuras indexadas 0–31; `a1` é casa escura e fica do lado das brancas. Tabuleiro imutável (tupla de 32 inteiros: 0 vazio, ±1 pedra, ±2 dama) para servir de chave de dicionário e facilitar o Minimax.
- **Vizinhança pré-calculada**: tabela com os raios diagonais de cada casa nas 4 direções, gerada uma vez.
- **Gerador**: busca em profundidade das sequências de captura (pedras capturam nas 4 direções; damas a distância, podendo pousar em qualquer casa livre atrás da peça capturada). Peças capturadas só saem do tabuleiro ao fim do lance e não podem ser saltadas duas vezes. Depois filtra pela **lei da maioria**. Sem capturas, gera lances simples.
- **Promoção**: só se o lance **termina** na última fileira.
- **Fim de jogo**: sem peças, sem lances, ou contador de 20 lances consecutivos de dama sem captura nem movimento de pedra.
- **Notação**: `c3-d4`, `c3xe5xg7`; conversão índice ↔ algébrica.
- **Testes**: posições montadas à mão para cada regra + contagem de nós (perft) em profundidades baixas para travar regressões.

### 4.2 Minimax

- **Busca**: negamax com poda alfa-beta, aprofundamento iterativo, limite de tempo e de profundidade (RF-MMX-03). Ordenação de lances: capturas primeiro, depois o melhor da iteração anterior.
- **Quiescência**: no horizonte, se o lado da vez tem captura, continua buscando só capturas.
- **Tabela de transposição**: dicionário por (tabuleiro, lado) dentro de uma análise. Fica para depois se a profundidade 8 em 1 s já for atingida sem ela.
- **Determinismo** (RF-MMX-04): ordem de lances estável; nos testes, o corte é por profundidade e não por tempo.
- **Análise por lance** (RF-MMX-01): a raiz busca cada lance com janela completa, para ter pontuação exata de todos, e não só do melhor.
- **Avaliação** (RF-MMX-02): soma ponderada em centésimos de pedra — pedra 100, dama 300, avanço, centro, mobilidade, peça ameaçada. Vitória forçada = ±(10000 − distância).
- **Rótulos** (RF-MMX-05): pela perda em relação ao melhor: 0 `melhor`; ≤ 30 `bom`; ≤ 100 `duvidoso`; > 100 `erro`. Limiares configuráveis.
- **Medição (T111, 2026-11-10, nesta máquina)**: com tabela de transposição, em 1 s a busca conclui profundidade **7 na abertura** e **10 ou mais no meio-jogo e no final**. Profundidade 8 na abertura leva ~1,7 s. Os padrões ficam em 1 s e profundidade máxima 8; na abertura o orçamento de tempo corta em 7, o que é aceito. Contagem de nós (perft) da posição inicial, profundidades 1–8: 7, 49, 302, 1469, 7473, 37628, 187302, 907836 — calculada por este motor, ainda não conferida com uma fonte externa.
- **Execução**: é CPU puro em Python, então roda em `ProcessPoolExecutor` (1 processo) para não disputar o GIL com a visão (RNF-10).

### 4.3 Visão

Pipeline por frame:

1. **Decodificar** o JPEG e reduzir para no máximo 1280 px de largura.
2. **Mão** (`mao.py`): Hand Landmarker em modo vídeo numa cópia reduzida. "Mão sobre o tabuleiro" = algum ponto da mão dentro do polígono do tabuleiro dilatado em ~10%. Se sim, o pipeline devolve `mao` e para.
3. **Retificar** (`localizacao.py`): homografia dos 4 cantos para uma imagem quadrada de 640×640; cada casa tem 80×80 px.
4. **Classificar** (`classificador.py`): para cada uma das 32 casas escuras, amostra o disco central (~60% da casa), extrai características em Lab (média e desvio de L, a, b) e compara com os 3 centroides aprendidos na calibração. Confiança = margem entre a classe mais próxima e a segunda.
5. **Estabilizar** (`estabilidade.py`): só emite `Observacao` quando a mesma leitura se repete em N frames seguidos sem mão e com todas as confianças acima do limiar.

Detalhes:

- **Cantos automáticos** (RF-VIS-01): máscara de saturação do tabuleiro marrom sobre a mesa clara (ver "Tabuleiro de referência" abaixo). Isso depende de a mesa ser pouco saturada, então **o ajuste manual dos 4 cantos na tela continua sendo o caminho garantido** e a detecção automática é o ponto de partida.
- **Calibração de cor** (RF-VIS-05): com a posição inicial montada, as casas escuras se dividem em 12 brancas, 12 pretas e 8 vazias, o que dá amostras rotuladas de graça para os três centroides. A calibração é refeita a cada sessão.
- **Atualização lenta**: depois de cada lance aceito, os centroides são ajustados levemente com as casas de alta confiança, para acompanhar mudança gradual de luz.
- **Paralaxe**: com câmera inclinada, a peça aparece deslocada em relação à casa. O disco de amostragem é deslocado na direção oposta à câmera por um fator estimado na calibração.
- **Deriva** (RF-VIS-09): a cada segundo, compara a borda do tabuleiro retificado com a da calibração; acima da tolerância, pede recalibração.
- **Interface plugável**: `Classificador` é um `Protocol` com `calibrar(imagem, rotulos)` e `classificar(imagem) -> list[(classe, confiança)]`. O MediaPipe Image Classifier customizado entra como segunda implementação, se necessário.
- **Execução**: thread dedicada com fila de tamanho 1 (o frame mais recente substitui o anterior), para o atraso nunca acumular.

#### Tabuleiro de referência

Fotos do tabuleiro real em `tests/fixtures/tabuleiro/` (vazio, duas inclinações). O que elas mostram e o que muda no projeto da visão:

| Observação | Consequência |
|---|---|
| Cerca de 20 × 20 cm, 8×8, casas de ~2,5 cm. | Tabuleiro pequeno: a mão cobre boa parte dele, o que reforça o bloqueio por mão. A ~35 cm de altura o telefone enquadra tudo com folga; a 1280 px de largura cada casa fica com 60–80 px, suficiente. |
| Casas escuras **marrom-cobre**, casas claras brancas, mesa branca/cinza. | O tabuleiro é a única região saturada da cena. Os cantos automáticos passam a usar **máscara de saturação + envoltória convexa + aproximação por quadrilátero**, que continua funcionando com peças em cima. Substitui a tentativa por grade de cantos internos. |
| Moldura marrom fina em volta, com margem branca entre ela e as casas. | A envoltória pega a moldura, não a área de jogo. A área de jogo é obtida encolhendo o quadrilátero por uma fração fixa, medida uma vez nestas fotos, e conferida pelo ajuste manual. |
| Logotipo nos dois cantos de **casa clara**. | Os outros dois cantos são casas escuras, e `a1` precisa ser escura: só existem 2 orientações válidas (giradas 180°). A calibração detecta os cantos escuros sozinha e só pergunta de que lado estão as brancas. O logotipo não atrapalha a classificação, porque casas claras nunca são classificadas. |
| Superfície **brilhante**, com reflexos claros sobre as casas marrons. | Um reflexo pode fazer casa vazia parecer peça clara. Usar mediana em vez de média no disco de amostragem, descartar pixels estourados e incluir a saturação nas características. Recomendar luz difusa, sem lâmpada direto acima. |
| Tabuleiro **dobrável**, com vinco no meio e bordas levantadas. | A homografia supõe um plano; o empenamento desloca as casas perto do vinco e das bordas. O disco de amostragem de 60% dá folga para isso. Recomendar prender o tabuleiro aberto (fita nas bordas). Se ainda errar, plano B: duas homografias, uma por metade, usando o vinco como divisor. |
| Desgaste e manchas nas casas. | Entra como ruído na calibração de casa vazia; o centroide de "vazia" usa as 8 casas vazias da posição inicial e depois todas as que ficarem livres. |

**Peças**: pretas e brancas (informado pelo usuário; ainda sem foto). Sobre a casa marrom-cobre isso dá três classes bem separadas:

| Classe | Luminância | Saturação |
|---|---|---|
| Peça branca | alta | baixa |
| Casa vazia (marrom) | média | **alta** |
| Peça preta | baixa | baixa |

A saturação separa "vazia" de "peça" e a luminância separa branca de preta, então o baseline de cor deve bastar e a borda circular fica como reserva. Pontos de atenção: reflexo especular numa casa vazia imita peça branca (luminância alta, saturação baixa) — por isso o descarte de pixels estourados e a mediana; e peça preta brilhante pode refletir a luz e clarear no centro.

**Falta**: foto com as 24 peças na posição inicial, do ângulo de uso, para medir a separação real e virar a fixture do CA-01. Não bloqueia M0–M2.

### 4.4 Casamento observação → lance

- Para o estado atual, pré-calcula `ocupacao_resultante -> lance` para todos os lances legais (ocupação = 32 valores vazia/branca/preta, sem distinguir dama).
- Observação igual ao estado atual: ignora (RF-JOG-05).
- Observação presente no dicionário: aplica o lance (RF-JOG-01). Dois lances com a mesma ocupação resultante só ocorrem quando capturam as mesmas peças por caminhos diferentes; são equivalentes e fica o primeiro.
- Caso contrário: entra em `intermediario` e espera. Se a observação seguinte casar, aplica. Se passar o timeout (padrão 15 s), vira `posicao_invalida` com a lista de diferenças casa a casa (RF-JOG-02/03).
- Com lance pendente de IA (RF-MOD-02/03), o esperado é só o lance anunciado; outro lance legal é reportado como divergência.

### 4.5 LLM (Gambi)

- **Cliente**: `AsyncOpenAI(base_url=f"{hub}/rooms/{sala}/v1", api_key="gambi")`. Participantes via `client.models.list()`.
- **Chamada**: tenta `responses.create`; se o hub ou o participante não suportar, usa `chat.completions.create` e lembra da escolha para as próximas (RF-LLM-09). Sem streaming, sem tools, sem JSON mode.
- **Prompt** (RF-LLM-03): instruções fixas (regras resumidas, formato da resposta) + posição em grade de texto 8×8 + lado da vez + últimos 6 lances + lista numerada de lances legais. No modo assistido, cada linha da lista ganha `| minimax: +0.35 (bom) | linha: e5xc3 b2xd4` (RF-LLM-03a).
- **Formato pedido**: primeira linha `LANCE: <número>`, segunda linha `MOTIVO: <uma frase>`.
- **Parser** (RF-LLM-04): procura `LANCE: n`; se não achar, aceita um lance em notação algébrica que esteja na lista; se não achar, aceita o único número isolado válido do texto. Qualquer outra coisa é inválida.
- **Retry e fallback** (RF-LLM-05/06): até 2 novas tentativas com mensagem corretiva curta; 409 (ocupado) espera 2 s antes de repetir; timeout, 404, 502, 503 ou tentativas esgotadas → melhor lance do Minimax, marcado como fallback.
- **Atalho**: um único lance legal não chama a LLM (RF-LLM-07).
- **Validação com hub real (T210, 2026-11-10)**: Gambi 0.6.0 nesta máquina, hub em `127.0.0.1:3210`, dois participantes via Ollama (`qwen2.5:7b` e `llama3.2`).
  - O hub aceitou **Responses e Chat Completions** para os dois participantes; o cliente ficou na Responses API.
  - Partida completa `qwen2.5:7b` × Minimax (profundidade 4): 52 lances em 99 s, **0% de fallback**, vitória do Minimax. Trecho `qwen2.5:7b` × `llama3.2`: 16 lances em 172 s, 0% de fallback.
  - A **primeira chamada a cada modelo demorou de 18 a mais de 60 s** (carga do modelo no Ollama) e estourou o tempo limite padrão. Rodar `dama checar-gambi` antes da partida aquece os modelos.
  - **Depois de um tempo esgotado, o participante continua ocupado** e a tentativa seguinte recebe 409. Por isso tempo esgotado vai direto para o fallback, sem nova tentativa.
  - Com dois modelos diferentes no mesmo Ollama, cada troca de lado pode recarregar o modelo: cerca de 10 s por lance no trecho LLM × LLM.
  - Os modelos escolhem um número válido, mas **o motivo que escrevem costuma ser inventado** (falam em captura num lance simples). O motivo deve ser exibido como opinião do modelo, não como fato.
  - `gambi ... --no-interactive` falha na versão 0.6.0 com "Ambiguous Syntax Error"; não usar essa opção.
- **Testes**: servidor falso compatível com OpenAI (FastAPI de teste) que devolve respostas roteirizadas: válida, lixo, 409, 503, lenta.

### 4.6 Orquestrador

Estados da partida: `preparando → em_jogo ⇄ aguardando_execucao`, com desvios para `posicao_invalida`, `pausada`, `recalibrar` e fim em `encerrada`.

- Cada lado tem um **controlador** com a mesma interface `async escolher(estado) -> Decisao`:
  - `ControladorLLM` (sem análise no IA × IA; com análise quando usado como conselheiro);
  - `ControladorMinimax` (RF-MMX-07);
  - `ControladorHumano` (não escolhe: o lance vem da câmera).
- **Laço de turno**:
  1. Juiz: dispara a análise Minimax da posição (usada para rotular o lance que vier, e como sugestão provisória no modo assistido).
  2. Se o lado é de IA: pede a decisão, publica o lance pendente e vai para `aguardando_execucao` até a câmera confirmar. No modo simulado, aplica direto.
  3. Se o lado é humano: no modo assistido e sendo o assistido, dispara a sugestão em paralelo; aplica o lance que a câmera casar.
  4. Registra lance + rótulo do juiz, verifica fim de jogo, troca o lado.
- Uma partida ativa por processo, em memória; salva em `dados/partidas/<id>.json` a cada lance, o que cobre reconexão (RF-CAP-05) e reinício do servidor.
- O orquestrador emite eventos (`estado`, `lance`, `sugestao`, `alerta`) que a camada web retransmite.

### 4.7 Web

- **Rotas HTTP**: `GET /` (página), `GET /api/saude`, `GET /api/gambi/participantes`, `POST /api/partida` (criar com modo e lados), `POST /api/partida/acao` (pausar, retomar, desfazer, forçar estado, encerrar, pedir sugestão), `GET /api/partida/exportar`.
- **WebSocket `/ws`**:
  - cliente → servidor: mensagens **binárias** = frame JPEG; mensagens **texto** = JSON (`ola` com papel `camera`/`jogador`/`espectador`, `cantos`, `calibrar_cores`).
  - servidor → cliente: JSON (`estado` completo ao conectar e a cada mudança, `visao` com status por frame aceito, `sugestao`, `alerta`).
- **Papéis** (RF-CAP-06, Q8): uma `camera` por partida; `jogador` vê as sugestões; `espectador` não vê.
- **Cliente** (`app.js`): `getUserMedia` com câmera traseira; desenha o vídeo num canvas, exporta JPEG (qualidade ~0,7) a 5 fps e só envia se o frame anterior já saiu (contrapressão simples); canvas de sobreposição com cantos arrastáveis; tabuleiro digital em grade CSS.
- **TLS** (`tls.py`): na primeira execução gera chave e certificado com os IPs locais no SAN, em `dados/tls/`; o uvicorn sobe com `ssl_keyfile`/`ssl_certfile`. O terminal mostra a URL `https://<ip>:8443` e o QR code.

### 4.8 Configuração

`.env` / variáveis `DAMA_*`: `GAMBI_HUB` (padrão `http://localhost:3000`), `GAMBI_SALA`, `PORTA` (8443), `LLM_TIMEOUT_S` (60), `LLM_TENTATIVAS` (2), `MINIMAX_TEMPO_S` (1.0), `MINIMAX_PROFUNDIDADE` (8), `VISAO_FRAMES_ESTAVEIS` (5), `VISAO_CONFIANCA_MIN`, `CAPTURA_TIMEOUT_S` (15), `GRAVAR_FRAMES` (falso).

## 5. Estratégia de testes

| Camada | Como |
|---|---|
| Regras | Unitários por regra + perft. Cobertura ≥ 90% (RNF-07). |
| Minimax | Posições táticas com resposta conhecida (CA-13); determinismo; respeito ao limite de tempo. |
| LLM | Parser com textos reais variados; retry/fallback contra o servidor falso (CA-10, CA-11, CA-15). |
| Casamento | Sequências de observações sintéticas, incluindo captura múltipla em etapas e lance ilegal (CA-03, CA-04). |
| Orquestrador | Partidas simuladas completas com controladores falsos e com Minimax × Minimax (CA-07, CA-14). |
| Visão | Fixtures: fotos e vídeos curtos gravados do tabuleiro real, com o estado esperado anotado em JSON (RNF-08). Mede a acurácia de RNF-01. Um modo `GRAVAR_FRAMES` serve para coletar essas fixtures. |
| Web | `httpx` + cliente WebSocket de teste: conectar, receber estado, reconectar (CA-12). |
| Manual | Roteiro com tabuleiro físico para CA-01, CA-02, CA-05, CA-08, CA-09, CA-16. |

Comandos: `uv run pytest`, `uv run ruff check`, `uv run ruff format`.

## 6. Marcos e ordem de entrega

| Marco | Entrega | Critérios |
|---|---|---|
| **M0 — Esqueleto** | `uv init`, dependências, estrutura de pastas, `ruff`/`pytest` rodando, `dama --help`. | — |
| **M1 — Regras + Minimax** | `regras/` e `minimax/` completos e testados. | CA-06, CA-13 |
| **M2 — Gambi + simulado** | `llm/`, controladores, orquestrador sem câmera, `dama simular`, `dama checar-gambi`. | CA-07, CA-10, CA-11, CA-14, CA-15 |
| **M3 — Captura e visão** | Servidor HTTPS, página com câmera, streaming, calibração de cantos e cores, tabuleiro digital ao vivo. | CA-01 |
| **M4 — Detecção de jogadas** | Mão, estabilidade, casamento, alertas, correção manual. | CA-02 a CA-05 |
| **M5 — Modos com câmera** | IA × IA físico, modo assistido, papéis de dispositivo, reconexão, exportação. | CA-08, CA-09, CA-12, CA-16 |

M1 e M2 não dependem de câmera e validam toda a lógica de jogo antes da parte mais incerta (visão). M3 começa com dois spikes curtos: API do Hand Landmarker no `mediapipe` 1.x e câmera do telefone via HTTPS autoassinado no Chrome Android e no Safari iOS.

## 7. Riscos técnicos e plano B

| Risco | Sinal | Plano B |
|---|---|---|
| Heurística de cor não atinge 99% por casa. | Medição nas fixtures do M3. | Mais características (borda circular por Hough); depois, MediaPipe Image Classifier treinado com as próprias fixtures. |
| Hand Landmarker não vê a mão (manga, luva, ângulo). | Leituras aceitas com braço em cena. | Segundo critério: diferença entre frames dentro do tabuleiro; a exigência de N frames estáveis já filtra parte. |
| Safari iOS recusa WebSocket seguro com certificado autoassinado. | Spike do M3. | `mkcert` com a CA instalada no aparelho. |
| Minimax em Python puro não chega à profundidade 8 em 1 s. | Benchmark no M1. | Tabela de transposição e melhor ordenação; aceitar profundidade 6; em último caso, representação em bitboards. |
| Hub Gambi sem Responses API no participante. | `checar-gambi` no M2. | Chat Completions (já previsto). |
| Modelo local demora mais que o timeout. | Taxa de fallback alta. | Timeout por lado configurável; prompt mais curto. |

## 8. Pré-requisitos externos (fora do código)

1. Instalar o Gambi: `irm https://raw.githubusercontent.com/arthurbm/gambi/main/scripts/install.ps1 | iex` ou `npm install -g gambi`.
2. Subir o hub: `gambi hub serve`.
3. Criar a sala: `gambi room create --name "Damas"` e anotar o código.
4. Entrar com ao menos um modelo, por exemplo Ollama: `gambi participant join --room <CODIGO> --participant-id brancas --model llama3`. Para IA × IA, um segundo participante com outro ID.
5. Telefone e PC na mesma rede; liberar a porta 8443 no firewall do Windows para a rede privada.
