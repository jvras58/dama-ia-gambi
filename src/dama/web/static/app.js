/**
 * Pagina do jogo. Por padrao, a partida e jogada pela tela: o servidor manda o estado
 * inteiro (casas, vez, lances legais) e a pagina so mostra e devolve o lance tocado.
 *
 * Com `?papel=camera`, a pagina abre a camera traseira, envia frames JPEG ao servidor
 * por WebSocket e mostra o que a visao reconheceu.
 *
 * Os cantos do tabuleiro sao sempre fracoes (0 a 1) da largura e da altura do
 * video, na ordem: superior esquerdo, superior direito, inferior direito, inferior
 * esquerdo.
 */
"use strict";

const LADO = 8;
const RAIO_DO_CANTO = 14;
const ALCANCE_DO_TOQUE = 48;
const ESPERA_PARA_RECONECTAR_MS = 2000;
const CANTOS_INICIAIS = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]];

const NOME_DO_ADVERSARIO = {
  humano: "Humano",
  minimax_facil: "Minimax fácil",
  minimax_medio: "Minimax médio",
  minimax_forte: "Minimax forte",
  llm: "LLM do Gambi",
};
const NOME_DA_ORIGEM = {
  humano: "humano",
  minimax: "Minimax",
  llm: "LLM",
  fallback: "Minimax (a LLM falhou)",
  unico: "único lance",
};
const FIM_DE_JOGO = {
  brancas: "Fim de jogo: vitória das brancas.",
  pretas: "Fim de jogo: vitória das pretas.",
  empate: "Fim de jogo: empate.",
};
const DAMA = "♛";

const PASSOS = {
  frame_invalido: "O servidor não conseguiu ler a imagem da câmera.",
  sem_cantos:
    "Passo 1: arraste os 4 pontos até as linhas da grade caírem sobre as casas e confirme.",
  sem_cores: "Passo 2: monte a posição inicial (12 peças de cada lado) e calibre as cores.",
  mao: "Mão sobre o tabuleiro: leitura em espera.",
  leitura: "Lendo o tabuleiro.",
};

const el = {
  conexao: document.getElementById("conexao"),
  papel: document.getElementById("papel"),
  fps: document.getElementById("fps"),
  duracao: document.getElementById("duracao"),
  passo: document.getElementById("passo"),
  aviso: document.getElementById("aviso"),
  camera: document.getElementById("camera"),
  video: document.getElementById("video"),
  sobreposicao: document.getElementById("sobreposicao"),
  confirmar: document.getElementById("confirmar"),
  refazer: document.getElementById("refazer"),
  calibrar: document.getElementById("calibrar"),
  inverter: document.getElementById("inverter"),
  salvar: document.getElementById("salvar"),
  previa: document.getElementById("previa"),
  digital: document.getElementById("digital"),
  resumo: document.getElementById("resumo"),
  paineis: document.getElementById("paineis"),
  jogo: document.getElementById("jogo"),
  situacao: document.getElementById("situacao"),
  tabuleiro: document.getElementById("tabuleiro"),
  dica: document.getElementById("dica"),
  pedirDica: document.getElementById("pedir-dica"),
  desfazer: document.getElementById("desfazer"),
  nova: document.getElementById("nova"),
  brancas: document.getElementById("brancas"),
  pretas: document.getElementById("pretas"),
  lances: document.getElementById("lances"),
};

const estado = {
  ws: null,
  papel: "espectador",
  captura: { fps: 5, largura: 1280, qualidade: 0.7 },
  temporizador: null,
  codificando: false,
  visao: null,
  cantos: CANTOS_INICIAIS.map((p) => [...p]),
  cantosMexidos: false,
  arrastando: -1,
  urlDaPrevia: null,
  partida: null,
  escolha: [],
  invertido: null,
  ladosMostrados: false,
};

const telaDeCaptura = document.createElement("canvas");

/** Papel pedido na URL (?papel=camera ou ?papel=espectador); sem parametro, jogador. */
function papelPedido() {
  const pedido = new URLSearchParams(location.search).get("papel");
  return ["camera", "jogador", "espectador"].includes(pedido) ? pedido : "jogador";
}

/** Mostra o estado da conexao na barra de saude. */
function mostrarConexao(texto, situacao) {
  el.conexao.textContent = texto;
  el.conexao.dataset.estado = situacao;
}

/** Mostra ou esconde a faixa de aviso. */
function mostrarAviso(texto) {
  el.aviso.textContent = texto;
  el.aviso.hidden = !texto;
}

/** Envia um comando em JSON, se a conexao estiver aberta. */
function enviar(mensagem) {
  if (estado.ws && estado.ws.readyState === WebSocket.OPEN) {
    estado.ws.send(JSON.stringify(mensagem));
  }
}

/** Abre o WebSocket e reconecta sozinho quando a conexao cai. */
function conectar() {
  const esquema = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${esquema}://${location.host}/ws`);
  ws.binaryType = "blob";
  estado.ws = ws;
  ws.addEventListener("open", () => {
    mostrarConexao("conectado", "ok");
    enviar({ tipo: "ola", papel: papelPedido() });
  });
  ws.addEventListener("message", (evento) => {
    if (typeof evento.data === "string") {
      receber(JSON.parse(evento.data));
    } else {
      mostrarPrevia(evento.data);
    }
  });
  ws.addEventListener("close", () => {
    mostrarConexao("reconectando", "erro");
    setTimeout(conectar, ESPERA_PARA_RECONECTAR_MS);
  });
}

/** Trata uma mensagem JSON do servidor. */
function receber(mensagem) {
  if (mensagem.tipo === "bem_vindo") {
    estado.papel = mensagem.papel;
    estado.captura = mensagem.captura;
    el.papel.textContent = mensagem.papel;
    const camera = mensagem.papel === "camera";
    el.camera.hidden = !camera;
    el.passo.hidden = !camera;
    el.paineis.hidden = !camera;
    el.jogo.hidden = camera;
    if (camera) {
      abrirCamera();
    }
    atualizarBotoes();
    desenharJogo();
  } else if (mensagem.tipo === "alerta") {
    mostrarAviso(mensagem.mensagem);
  } else if (mensagem.tipo === "visao") {
    receberVisao(mensagem);
  } else if (mensagem.tipo === "partida") {
    receberPartida(mensagem);
  }
}

/** Atualiza a tela com o que a visao tirou do ultimo frame. */
function receberVisao(visao) {
  estado.visao = visao;
  el.paineis.hidden = false;
  el.fps.textContent = `${visao.fps.toFixed(1)} fps`;
  el.duracao.textContent = `${Math.round(visao.duracao_ms)} ms`;
  if (estado.papel === "camera") {
    el.passo.textContent = PASSOS[visao.situacao] || visao.situacao;
  }
  if (visao.aviso) {
    mostrarAviso(visao.aviso);
  }
  if (visao.cantos) {
    estado.cantos = visao.cantos.map((p) => [...p]);
    estado.cantosMexidos = false;
  } else if (visao.cantos_sugeridos && !estado.cantosMexidos && estado.arrastando < 0) {
    estado.cantos = visao.cantos_sugeridos.map((p) => [...p]);
  }
  atualizarBotoes();
  desenharCantos();
  desenharTabuleiro(visao);
}

/** Mostra so os botoes que fazem sentido no passo atual. */
function atualizarBotoes() {
  const camera = estado.papel === "camera";
  const situacao = estado.visao ? estado.visao.situacao : "sem_cantos";
  const comCantos = Boolean(estado.visao && estado.visao.cantos);
  el.confirmar.hidden = !camera || comCantos;
  el.refazer.hidden = !camera || !comCantos;
  el.calibrar.hidden = !camera || !comCantos;
  el.calibrar.textContent = situacao === "leitura" ? "Recalibrar cores" : "Calibrar cores";
  el.calibrar.classList.toggle("principal", situacao !== "leitura");
  el.inverter.hidden = !camera || situacao !== "leitura";
  el.salvar.hidden = !camera;
}

/** Troca a imagem da previa do tabuleiro retificado, liberando a anterior. */
function mostrarPrevia(blob) {
  if (estado.urlDaPrevia) {
    URL.revokeObjectURL(estado.urlDaPrevia);
  }
  estado.urlDaPrevia = URL.createObjectURL(blob);
  el.previa.src = estado.urlDaPrevia;
}

/** Pede a camera traseira e comeca a enviar frames. */
async function abrirCamera() {
  if (el.video.srcObject) {
    return;
  }
  try {
    const fluxo = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    });
    el.video.srcObject = fluxo;
    await el.video.play();
    ajustarSobreposicao();
    clearInterval(estado.temporizador);
    estado.temporizador = setInterval(enviarFrame, 1000 / estado.captura.fps);
  } catch (erro) {
    el.passo.textContent = "Não foi possível abrir a câmera.";
    mostrarAviso(`Permita o uso da câmera nesta página e recarregue. (${erro.name})`);
  }
}

/**
 * Envia um frame JPEG. Se o anterior ainda nao saiu do aparelho ou ainda esta sendo
 * codificado, este e pulado: assim o atraso nunca acumula.
 */
function enviarFrame() {
  const ws = estado.ws;
  const video = el.video;
  if (!ws || ws.readyState !== WebSocket.OPEN || ws.bufferedAmount > 0) {
    return;
  }
  if (estado.codificando || !video.videoWidth) {
    return;
  }
  const escala = Math.min(1, estado.captura.largura / video.videoWidth);
  telaDeCaptura.width = Math.round(video.videoWidth * escala);
  telaDeCaptura.height = Math.round(video.videoHeight * escala);
  telaDeCaptura.getContext("2d").drawImage(video, 0, 0, telaDeCaptura.width, telaDeCaptura.height);
  estado.codificando = true;
  telaDeCaptura.toBlob(
    (blob) => {
      estado.codificando = false;
      if (blob && ws.readyState === WebSocket.OPEN) {
        ws.send(blob);
      }
    },
    "image/jpeg",
    estado.captura.qualidade,
  );
}

/** Deixa a tela de desenho com o mesmo tamanho, em pixels, do video exibido. */
function ajustarSobreposicao() {
  const caixa = el.sobreposicao.getBoundingClientRect();
  const densidade = window.devicePixelRatio || 1;
  el.sobreposicao.width = Math.round(caixa.width * densidade);
  el.sobreposicao.height = Math.round(caixa.height * densidade);
  desenharCantos();
}

/**
 * Funcao que leva um ponto (u, v) do quadrado unitario ao quadrilatero `pontos`,
 * respeitando a perspectiva. Os pontos seguem a ordem dos cantos: (0,0), (1,0),
 * (1,1) e (0,1). E a transformacao projetiva de quadrado para quadrilatero.
 */
function projecao(pontos) {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = pontos;
  const sx = x0 - x1 + x2 - x3;
  const sy = y0 - y1 + y2 - y3;
  const dx1 = x1 - x2;
  const dx2 = x3 - x2;
  const dy1 = y1 - y2;
  const dy2 = y3 - y2;
  const divisor = dx1 * dy2 - dx2 * dy1 || 1e-9;
  const g = (sx * dy2 - dx2 * sy) / divisor;
  const h = (dx1 * sy - sx * dy1) / divisor;
  const a = x1 - x0 + g * x1;
  const b = x3 - x0 + h * x3;
  const d = y1 - y0 + g * y1;
  const e = y3 - y0 + h * y3;
  return (u, v) => {
    const w = g * u + h * v + 1;
    return [(a * u + b * v + x0) / w, (d * u + e * v + y0) / w];
  };
}

/**
 * Desenha as linhas internas da grade 8x8 dentro do quadrilatero. Quando os cantos
 * estao certos, cada linha cai sobre a divisa entre duas fileiras de casas.
 */
function desenharGrade(ctx, pontos, densidade) {
  const levar = projecao(pontos);
  ctx.lineWidth = 1.5 * densidade;
  ctx.beginPath();
  for (let i = 1; i < LADO; i += 1) {
    const t = i / LADO;
    ctx.moveTo(...levar(t, 0));
    ctx.lineTo(...levar(t, 1));
    ctx.moveTo(...levar(0, t));
    ctx.lineTo(...levar(1, t));
  }
  ctx.stroke();
}

/**
 * Desenha o contorno do tabuleiro com a grade 8x8 e, enquanto nao confirmado, os
 * pontos de arrasto.
 */
function desenharCantos() {
  const tela = el.sobreposicao;
  const ctx = tela.getContext("2d");
  ctx.clearRect(0, 0, tela.width, tela.height);
  if (estado.papel !== "camera" && !(estado.visao && estado.visao.cantos)) {
    return;
  }
  const densidade = window.devicePixelRatio || 1;
  const confirmados = Boolean(estado.visao && estado.visao.cantos);
  const pontos = estado.cantos.map(([x, y]) => [x * tela.width, y * tela.height]);
  ctx.lineWidth = 3 * densidade;
  ctx.strokeStyle = confirmados ? "#4ade80" : "#f59e0b";
  ctx.beginPath();
  pontos.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
  ctx.stroke();
  desenharGrade(ctx, pontos, densidade);
  if (confirmados) {
    return;
  }
  ctx.fillStyle = "rgb(245 158 11 / 85%)";
  ctx.strokeStyle = "#1c1917";
  ctx.lineWidth = 2 * densidade;
  for (const [x, y] of pontos) {
    ctx.beginPath();
    ctx.arc(x, y, RAIO_DO_CANTO * densidade, 0, 2 * Math.PI);
    ctx.fill();
    ctx.stroke();
  }
}

/** Posicao do toque como fracao da largura e da altura do video. */
function posicaoDoToque(evento) {
  const caixa = el.sobreposicao.getBoundingClientRect();
  return [
    Math.min(1, Math.max(0, (evento.clientX - caixa.left) / caixa.width)),
    Math.min(1, Math.max(0, (evento.clientY - caixa.top) / caixa.height)),
  ];
}

/** Indice do canto mais proximo do toque, ou -1 se nenhum estiver ao alcance. */
function cantoMaisProximo(evento) {
  const caixa = el.sobreposicao.getBoundingClientRect();
  const [tx, ty] = posicaoDoToque(evento);
  let melhor = -1;
  let menor = ALCANCE_DO_TOQUE;
  estado.cantos.forEach(([x, y], i) => {
    const distancia = Math.hypot((x - tx) * caixa.width, (y - ty) * caixa.height);
    if (distancia < menor) {
      menor = distancia;
      melhor = i;
    }
  });
  return melhor;
}

/** Liga o arrasto dos cantos, que so vale antes da confirmacao. */
function prepararArrasto() {
  const tela = el.sobreposicao;
  tela.addEventListener("pointerdown", (evento) => {
    if (estado.papel !== "camera" || (estado.visao && estado.visao.cantos)) {
      return;
    }
    estado.arrastando = cantoMaisProximo(evento);
    if (estado.arrastando >= 0) {
      tela.setPointerCapture(evento.pointerId);
      estado.cantosMexidos = true;
    }
  });
  tela.addEventListener("pointermove", (evento) => {
    if (estado.arrastando >= 0) {
      estado.cantos[estado.arrastando] = posicaoDoToque(evento);
      desenharCantos();
    }
  });
  const soltar = () => {
    estado.arrastando = -1;
  };
  tela.addEventListener("pointerup", soltar);
  tela.addEventListener("pointercancel", soltar);
}

/** Cria as 64 casas do tabuleiro digital, com a linha 8 em cima. */
function montarTabuleiro() {
  for (let linha = LADO - 1; linha >= 0; linha -= 1) {
    for (let coluna = 0; coluna < LADO; coluna += 1) {
      const casa = document.createElement("div");
      casa.className = "casa";
      if ((linha + coluna) % 2 === 0) {
        casa.classList.add("escura");
        casa.dataset.indice = String(linha * (LADO / 2) + Math.floor(coluna / 2));
      }
      el.digital.append(casa);
    }
  }
}

/** Pinta no tabuleiro digital a ocupacao de cada casa e destaca as duvidosas. */
function desenharTabuleiro(visao) {
  const duvidosas = new Set(visao.duvidosas);
  el.digital.classList.toggle("espelhado", Boolean(visao.espelhado));
  for (const casa of el.digital.querySelectorAll(".casa.escura")) {
    const indice = Number(casa.dataset.indice);
    const lida = visao.casas[indice];
    casa.dataset.ocupacao = lida ? lida.ocupacao : "vazia";
    casa.classList.toggle("duvidosa", duvidosas.has(indice));
  }
  if (visao.situacao !== "leitura") {
    el.resumo.textContent = "Aguardando a calibração.";
    return;
  }
  const brancas = visao.casas.filter((c) => c.ocupacao === "branca").length;
  const pretas = visao.casas.filter((c) => c.ocupacao === "preta").length;
  const duvida = duvidosas.size ? `, ${duvidosas.size} casa(s) em dúvida` : "";
  el.resumo.textContent = `${brancas} brancas e ${pretas} pretas${duvida}.`;
}

/**
 * Preenche as duas listas de quem controla cada lado com as opcoes do servidor e
 * marca os lados da partida. A opcao de LLM fica desabilitada sem o Gambi.
 */
function montarLados(partida) {
  for (const [lado, lista] of [["brancas", el.brancas], ["pretas", el.pretas]]) {
    lista.replaceChildren();
    for (const opcao of partida.opcoes) {
      const item = new Option(NOME_DO_ADVERSARIO[opcao.adversario], opcao.valor);
      item.disabled = opcao.adversario === "llm" && !partida.gambi;
      lista.append(item);
    }
    lista.value = partida.lados[lado];
  }
}

/**
 * Cria as 64 casas do tabuleiro de jogo. Com `invertido`, as pretas ficam embaixo,
 * para quem joga com elas.
 */
function montarJogo(invertido) {
  estado.invertido = invertido;
  el.tabuleiro.replaceChildren();
  for (let i = 0; i < LADO; i += 1) {
    for (let j = 0; j < LADO; j += 1) {
      const linha = invertido ? i : LADO - 1 - i;
      const coluna = invertido ? LADO - 1 - j : j;
      const casa = document.createElement("div");
      casa.className = "casa";
      if ((linha + coluna) % 2 === 0) {
        casa.classList.add("escura");
        casa.dataset.indice = String(linha * (LADO / 2) + Math.floor(coluna / 2));
      }
      el.tabuleiro.append(casa);
    }
  }
}

/** Guarda o estado da partida vindo do servidor e redesenha o jogo. */
function receberPartida(partida) {
  estado.partida = partida;
  estado.escolha = [];
  if (!estado.ladosMostrados) {
    montarLados(partida);
    estado.ladosMostrados = true;
  }
  desenharJogo();
  desenharLances(partida);
}

/** Lances legais que comecam pelas casas ja tocadas. */
function candidatos() {
  const partida = estado.partida;
  if (!partida || !partida.humano_na_vez || estado.papel === "espectador") {
    return [];
  }
  return partida.legais.filter((lance) => estado.escolha.every((c, i) => lance.casas[i] === c));
}

/** Frase sobre o momento da partida: de quem e a vez, quem pensa, quem venceu. */
function situacaoDoJogo(partida) {
  if (!partida || !partida.ativa) {
    return "Escolha quem joga de cada lado e toque em Nova partida.";
  }
  if (partida.estado === "encerrada") {
    return FIM_DE_JOGO[partida.resultado] || "Fim de jogo.";
  }
  if (partida.pensando && !partida.humano_na_vez) {
    return `As ${partida.vez} estão pensando…`;
  }
  if (partida.humano_na_vez) {
    const captura = partida.legais.some((lance) => lance.capturas.length);
    const espera = partida.pensando ? " Buscando a dica…" : "";
    return `Vez das ${partida.vez}.${captura ? " A captura é obrigatória." : ""}${espera}`;
  }
  return `Vez das ${partida.vez}.`;
}

/** Desenha as pecas, os destaques, a situacao e os botoes do jogo pela tela. */
function desenharJogo() {
  const partida = estado.partida;
  el.situacao.textContent = situacaoDoJogo(partida);
  const lados = partida ? partida.lados : null;
  const invertido = Boolean(lados) && lados.pretas === "humano" && lados.brancas !== "humano";
  if (estado.invertido !== invertido) {
    montarJogo(invertido);
  }
  const possiveis = candidatos();
  const passo = estado.escolha.length;
  const moveis = new Set(passo ? [] : possiveis.map((lance) => lance.casas[0]));
  const destinos = new Set(passo ? possiveis.map((lance) => lance.casas[passo]) : []);
  const ultimo = new Set(partida ? partida.ultimo : []);
  const sugeridas = new Set(partida && partida.dica ? partida.dica.casas : []);
  for (const casa of el.tabuleiro.querySelectorAll(".casa.escura")) {
    const indice = Number(casa.dataset.indice);
    const peca = partida ? partida.casas[indice] : 0;
    casa.replaceChildren();
    if (peca) {
      const disco = document.createElement("span");
      disco.className = `peca ${peca > 0 ? "branca" : "preta"}`;
      disco.textContent = Math.abs(peca) === 2 ? DAMA : "";
      casa.append(disco);
    }
    casa.classList.toggle("ultimo", ultimo.has(indice));
    casa.classList.toggle("sugerida", sugeridas.has(indice));
    casa.classList.toggle("movel", moveis.has(indice));
    casa.classList.toggle("escolhida", estado.escolha.includes(indice));
    casa.classList.toggle("destino", destinos.has(indice));
  }
  const espectador = estado.papel === "espectador";
  const podeJogar = Boolean(partida && partida.humano_na_vez) && !espectador;
  const haHumano = Boolean(partida) && Object.values(partida.lados).includes("humano");
  el.pedirDica.hidden = !podeJogar;
  el.pedirDica.disabled = Boolean(partida && partida.pensando);
  el.desfazer.hidden = !partida || !partida.lances.length || !haHumano || espectador;
  el.nova.hidden = espectador;
  const dica = partida ? partida.dica : null;
  el.dica.hidden = !dica;
  if (dica) {
    const origem = NOME_DA_ORIGEM[dica.origem] || dica.origem;
    const motivo = dica.motivo ? ` ${dica.motivo}` : "";
    const daLlm = dica.origem === "llm" && dica.minimax;
    const nota = daLlm ? ` Minimax: ${dica.minimax}.` : "";
    el.dica.textContent = `Dica (${origem}): ${dica.lance}.${motivo}${nota}`;
  }
}

/** Lista os lances jogados, com quem jogou e a nota do juiz. */
function desenharLances(partida) {
  el.lances.replaceChildren();
  for (const lance of partida.lances) {
    const item = document.createElement("li");
    item.dataset.rotulo = lance.rotulo || "";
    const origem = NOME_DA_ORIGEM[lance.origem] || lance.origem;
    const partes = [
      ["numero", `${lance.numero}.`],
      ["texto", lance.lance],
      ["detalhe", [origem, lance.rotulo].filter(Boolean).join(" · ")],
    ];
    for (const [classe, texto] of partes) {
      const trecho = document.createElement("span");
      trecho.className = classe;
      trecho.textContent = texto;
      item.append(trecho);
    }
    item.title = lance.motivo;
    el.lances.append(item);
  }
  el.lances.scrollTop = el.lances.scrollHeight;
}

/**
 * Trata o toque numa casa. O primeiro toque escolhe a peca; os seguintes seguem o
 * caminho do lance, casa a casa, o que cobre as capturas em sequencia. Quando as
 * casas tocadas formam um lance inteiro, ele e enviado ao servidor.
 */
function tocarCasa(indice) {
  const passo = estado.escolha.length;
  const continua = passo > 0 && candidatos().some((lance) => lance.casas[passo] === indice);
  if (continua) {
    estado.escolha.push(indice);
    const completo = candidatos().find((lance) => lance.casas.length === estado.escolha.length);
    if (completo) {
      estado.escolha = [];
      mostrarAviso("");
      enviar({ tipo: "jogar", lance: completo.texto });
    }
  } else {
    estado.escolha = [];
    if (candidatos().some((lance) => lance.casas[0] === indice)) {
      estado.escolha = [indice];
    }
  }
  desenharJogo();
}

/** Liga os toques do tabuleiro e os botoes do jogo pela tela. */
function prepararJogo() {
  el.tabuleiro.addEventListener("click", (evento) => {
    const casa = evento.target.closest(".casa.escura");
    if (casa) {
      tocarCasa(Number(casa.dataset.indice));
    }
  });
  el.nova.addEventListener("submit", (evento) => {
    evento.preventDefault();
    mostrarAviso("");
    enviar({ tipo: "nova_partida", brancas: el.brancas.value, pretas: el.pretas.value });
  });
  el.pedirDica.addEventListener("click", () => enviar({ tipo: "dica" }));
  el.desfazer.addEventListener("click", () => {
    mostrarAviso("");
    enviar({ tipo: "desfazer" });
  });
}

/** Liga os botoes aos comandos do servidor. */
function prepararBotoes() {
  el.confirmar.addEventListener("click", () => {
    mostrarAviso("");
    enviar({ tipo: "cantos", pontos: estado.cantos });
  });
  el.refazer.addEventListener("click", () => {
    estado.cantosMexidos = false;
    enviar({ tipo: "limpar_cantos" });
  });
  el.calibrar.addEventListener("click", () => {
    mostrarAviso("");
    enviar({ tipo: "calibrar_cores" });
  });
  el.inverter.addEventListener("click", () => enviar({ tipo: "inverter_lados" }));
  el.salvar.addEventListener("click", () => enviar({ tipo: "salvar_frame" }));
}

montarTabuleiro();
desenharJogo();
prepararJogo();
prepararArrasto();
prepararBotoes();
window.addEventListener("resize", ajustarSobreposicao);
el.video.addEventListener("loadedmetadata", ajustarSobreposicao);
conectar();
