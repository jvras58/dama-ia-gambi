/**
 * Pagina do telefone: abre a camera traseira, envia frames JPEG ao servidor por
 * WebSocket e mostra o que a visao reconheceu.
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

const PASSOS = {
  frame_invalido: "O servidor não conseguiu ler a imagem da câmera.",
  sem_cantos: "Passo 1: arraste os 4 pontos até os cantos da área de jogo e confirme.",
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
};

const telaDeCaptura = document.createElement("canvas");

/** Papel pedido na URL (?papel=espectador); sem parametro, o aparelho e a camera. */
function papelPedido() {
  const pedido = new URLSearchParams(location.search).get("papel");
  return ["camera", "jogador", "espectador"].includes(pedido) ? pedido : "camera";
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
    el.camera.hidden = mensagem.papel !== "camera";
    if (mensagem.papel === "camera") {
      abrirCamera();
    } else {
      el.passo.textContent = "Acompanhando a partida.";
    }
    atualizarBotoes();
  } else if (mensagem.tipo === "alerta") {
    mostrarAviso(mensagem.mensagem);
  } else if (mensagem.tipo === "visao") {
    receberVisao(mensagem);
  }
}

/** Atualiza a tela com o que a visao tirou do ultimo frame. */
function receberVisao(visao) {
  estado.visao = visao;
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

/** Desenha o contorno do tabuleiro e, enquanto nao confirmado, os pontos de arrasto. */
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
prepararArrasto();
prepararBotoes();
window.addEventListener("resize", ajustarSobreposicao);
el.video.addEventListener("loadedmetadata", ajustarSobreposicao);
conectar();
