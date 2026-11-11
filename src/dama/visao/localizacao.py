"""Localizacao do tabuleiro na imagem e retificacao para uma vista de topo.

O tabuleiro de referencia tem casas e moldura marrons. Sobre uma mesa sem cor, ele e a
unica regiao colorida da cena, e a localizacao automatica usa isso (mascara de croma no
espaco Lab). Sobre um fundo colorido, como uma toalha, o que vale e a maior mancha de
cor diferente da do fundo, medida na borda da imagem. Nos dois casos segue-se a
envoltoria convexa e o quadrilatero. A localizacao e so o ponto de partida: o ajuste
manual dos cantos na tela continua sendo o caminho garantido.

A envoltoria pega a moldura do tabuleiro, que continua visivel com as pecas em cima.
A area de jogo e obtida encolhendo o quadrilatero por uma fracao fixa
(`visao_margem_da_moldura`), medida nas fotos de `tests/fixtures/tabuleiro/`.

Na imagem retificada, a casa da linha `l` e coluna `c` da imagem (contadas a partir do
canto superior esquerdo) ocupa um quadrado de `lado / 8` pixels.
"""

from typing import Final

import cv2
import numpy as np
from numpy.typing import NDArray

from dama.config import obter_config
from dama.regras.tabuleiro import LADO, linha_coluna
from dama.regras.tipos import Casa
from dama.visao.tipos import Cantos, Imagem, LadoDasBrancas, Ponto

_QUADRADO_UNITARIO: Final[tuple[Ponto, ...]] = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
_CENTRO_DO_LAB: Final[float] = 128.0
_TOLERANCIA_DO_POLIGONO: Final[float] = 0.01
_PARALELAS: Final[float] = 1e-9
_MINIMO_DE_PONTOS_POR_LADO: Final[int] = 10


def reduzir(imagem: Imagem) -> Imagem:
    """Reduz a imagem para no maximo `visao_largura_max` pixels de largura."""
    largura_max = obter_config().visao_largura_max
    altura, largura = imagem.shape[:2]
    if largura <= largura_max:
        return imagem
    escala = largura_max / largura
    reduzida: Imagem = cv2.resize(
        imagem, (largura_max, round(altura * escala)), interpolation=cv2.INTER_AREA
    ).astype(np.uint8)
    return reduzida


def croma(imagem: Imagem) -> NDArray[np.float32]:
    """Quao colorido e cada pixel: distancia ao eixo cinza no espaco Lab."""
    lab = cv2.cvtColor(imagem, cv2.COLOR_BGR2LAB).astype(np.float32)
    a = lab[:, :, 1] - _CENTRO_DO_LAB
    b = lab[:, :, 2] - _CENTRO_DO_LAB
    resultado: NDArray[np.float32] = np.sqrt(a * a + b * b)
    return resultado


def ordenar_cantos(pontos: NDArray[np.float32]) -> Cantos:
    """Poe quatro pontos na ordem: sup. esquerdo, sup. direito, inf. direito, inf. esquerdo.

    Ordena pelo angulo em torno do centro e comeca pelo ponto de menor x + y.
    """
    centro = pontos.mean(axis=0)
    angulos = np.arctan2(pontos[:, 1] - centro[1], pontos[:, 0] - centro[0])
    em_volta = pontos[np.argsort(angulos)]
    inicio = int(np.argmin(em_volta.sum(axis=1)))
    girado = np.roll(em_volta, -inicio, axis=0)
    return _para_cantos(girado)


def _para_cantos(pontos: NDArray[np.float32]) -> Cantos:
    """Converte uma matriz 4x2 na tupla `Cantos`."""
    p = [(float(x), float(y)) for x, y in pontos]
    return (p[0], p[1], p[2], p[3])


def _matriz(cantos: Cantos | tuple[Ponto, ...]) -> NDArray[np.float32]:
    """Converte cantos numa matriz 4x2 de float32, como o OpenCV espera."""
    return np.array(cantos, dtype=np.float32)


def _quatro_lados(envoltoria: NDArray[np.int32]) -> Cantos | None:
    """Quadrilatero formado pelos quatro maiores lados de um poligono convexo.

    Um canto arredondado, gasto ou escondido deixa a envoltoria com mais de quatro
    lados. Prolongar os quatro lados maiores e cruza-los devolve os cantos verdadeiros.
    """
    perimetro = cv2.arcLength(envoltoria, True)
    poligono = cv2.approxPolyDP(envoltoria, _TOLERANCIA_DO_POLIGONO * perimetro, True)
    vertices = poligono.reshape(-1, 2).astype(np.float64)
    quantos = len(vertices)
    if quantos < 4:
        return None
    comprimentos = [
        float(np.linalg.norm(vertices[(i + 1) % quantos] - vertices[i])) for i in range(quantos)
    ]
    maiores = sorted(sorted(range(quantos), key=lambda i: -comprimentos[i])[:4])
    cantos: list[Ponto] = []
    for posicao, i in enumerate(maiores):
        j = maiores[(posicao + 1) % 4]
        cruzamento = _cruzar(
            vertices[i], vertices[(i + 1) % quantos], vertices[j], vertices[(j + 1) % quantos]
        )
        if cruzamento is None:
            return None
        cantos.append(cruzamento)
    return ordenar_cantos(np.array(cantos, dtype=np.float32))


def _ajustar_lados(envoltoria: NDArray[np.int32], inicial: Cantos) -> Cantos | None:
    """Refina o quadrilatero ajustando uma reta a todos os pontos de cada lado.

    O tabuleiro e dobravel e as bordas empenam: um lado curvo nao e bem representado
    pelo seu maior trecho reto. Cada ponto do contorno da envoltoria e atribuido ao
    lado mais proximo do quadrilatero inicial, e cada lado vira a reta de minimos
    quadrados dos seus pontos. Devolve None se algum lado ficar sem pontos.
    """
    contorno = np.zeros((int(envoltoria[:, 0, 1].max()) + 2, int(envoltoria[:, 0, 0].max()) + 2))
    cv2.polylines(contorno, [envoltoria], True, 1.0, 1)
    ys, xs = np.nonzero(contorno)
    pontos = np.stack([xs, ys], axis=1).astype(np.float64)
    quina = np.array(inicial, dtype=np.float64)
    distancias = np.stack(
        [_distancia_ao_segmento(pontos, quina[i], quina[(i + 1) % 4]) for i in range(4)], axis=1
    )
    dono = distancias.argmin(axis=1)
    retas: list[tuple[NDArray[np.float64], NDArray[np.float64]]] = []
    for lado in range(4):
        do_lado = pontos[dono == lado]
        if len(do_lado) < _MINIMO_DE_PONTOS_POR_LADO:
            return None
        vx, vy, x0, y0 = cv2.fitLine(do_lado.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        base = np.array([x0, y0], dtype=np.float64)
        retas.append((base, base + np.array([vx, vy], dtype=np.float64)))
    cantos: list[Ponto] = []
    for lado in range(4):
        cruzamento = _cruzar(*retas[lado - 1], *retas[lado])
        if cruzamento is None:
            return None
        cantos.append(cruzamento)
    return ordenar_cantos(np.array(cantos, dtype=np.float32))


def _distancia_ao_segmento(
    pontos: NDArray[np.float64], a: NDArray[np.float64], b: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Distancia de cada ponto ao segmento que vai de `a` a `b`."""
    direcao = b - a
    comprimento = float(direcao @ direcao)
    t = np.clip(((pontos - a) @ direcao) / max(comprimento, _PARALELAS), 0.0, 1.0)
    proximo = a + t[:, None] * direcao
    resultado: NDArray[np.float64] = np.linalg.norm(pontos - proximo, axis=1)
    return resultado


def _cruzar(
    a0: NDArray[np.float64],
    a1: NDArray[np.float64],
    b0: NDArray[np.float64],
    b1: NDArray[np.float64],
) -> Ponto | None:
    """Ponto em que a reta por `a0` e `a1` cruza a reta por `b0` e `b1`; None se paralelas."""
    da, db = a1 - a0, b1 - b0
    determinante = float(da[0] * db[1] - da[1] * db[0])
    if abs(determinante) < _PARALELAS:
        return None
    t = float((b0[0] - a0[0]) * db[1] - (b0[1] - a0[1]) * db[0]) / determinante
    return (float(a0[0] + t * da[0]), float(a0[1] + t * da[1]))


def cor_do_fundo(lab: NDArray[np.float32]) -> NDArray[np.float32]:
    """Cor mediana (Lab) de uma faixa em volta da imagem, onde costuma estar o fundo."""
    altura, largura = lab.shape[:2]
    faixa = max(1, round(min(altura, largura) * obter_config().visao_faixa_do_fundo))
    borda = np.concatenate(
        [
            lab[:faixa].reshape(-1, 3),
            lab[-faixa:].reshape(-1, 3),
            lab[:, :faixa].reshape(-1, 3),
            lab[:, -faixa:].reshape(-1, 3),
        ]
    )
    fundo: NDArray[np.float32] = np.median(borda, axis=0).astype(np.float32)
    return fundo


def _abrir(mascara: NDArray[np.uint8], fracao: float) -> NDArray[np.uint8]:
    """Abertura morfologica com nucleo de `fracao` da largura; apaga o que e mais fino."""
    lado_do_nucleo = round(mascara.shape[1] * fracao)
    if lado_do_nucleo <= 1:
        return mascara
    nucleo = cv2.getStructuringElement(cv2.MORPH_RECT, (lado_do_nucleo, lado_do_nucleo))
    return cv2.morphologyEx(mascara, cv2.MORPH_OPEN, nucleo).astype(np.uint8)


def _mascara_em_fundo_neutro(imagem: Imagem) -> NDArray[np.bool_]:
    """Pixels do tabuleiro quando o fundo nao tem cor: tudo o que e colorido.

    Abertura pequena para limpar o ruido e descarte das manchas menores que
    `visao_mancha_minima`. A moldura marrom garante o contorno mesmo com pecas.
    """
    config = obter_config()
    area_da_imagem = imagem.shape[0] * imagem.shape[1]
    mascara = _abrir(
        (croma(imagem) > config.visao_croma_min).astype(np.uint8), config.visao_abertura
    )
    quantas, rotulos, dados, _ = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    grandes = [
        i
        for i in range(1, quantas)
        if dados[i, cv2.CC_STAT_AREA] >= config.visao_mancha_minima * area_da_imagem
    ]
    resultado: NDArray[np.bool_] = np.isin(rotulos, grandes)
    return resultado


def _mascara_em_fundo_colorido(
    lab: NDArray[np.float32], fundo: NDArray[np.float32]
) -> NDArray[np.bool_]:
    """Pixels do tabuleiro quando o fundo e colorido: a maior mancha diferente do fundo.

    Sobre uma toalha colorida, o croma nao separa nada. O que separa e a distancia de
    cor ao fundo, com a luminosidade pesando menos para as sombras nao contarem. Uma
    abertura maior apaga a estampa do tecido, e so a maior mancha e mantida.
    """
    config = obter_config()
    diferenca = lab - fundo
    diferenca[:, :, 0] *= config.visao_peso_da_luz_no_fundo
    distancia = np.sqrt((diferenca * diferenca).sum(axis=2))
    mascara = _abrir(
        (distancia > config.visao_distancia_do_fundo).astype(np.uint8),
        config.visao_abertura_no_fundo,
    )
    quantas, rotulos, dados, _ = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    if quantas < 2:
        return np.zeros(mascara.shape, dtype=np.bool_)
    maior = 1 + int(np.argmax(dados[1:, cv2.CC_STAT_AREA]))
    resultado: NDArray[np.bool_] = rotulos == maior
    return resultado


def localizar_moldura(imagem: Imagem) -> Cantos | None:
    """Cantos do contorno do tabuleiro, ou None se nao houver um quadrilatero.

    Passos:
    1. cor do fundo, medida na borda da imagem;
    2. mascara do tabuleiro: em fundo sem cor (croma abaixo de `visao_croma_min`),
       os pixels coloridos; em fundo colorido, a maior mancha diferente do fundo;
    3. envoltoria convexa da mascara, que precisa ocupar ao menos
       `visao_area_minima` da imagem;
    4. quadrilatero pelos quatro maiores lados da envoltoria.
    """
    config = obter_config()
    area_da_imagem = imagem.shape[0] * imagem.shape[1]
    lab = cv2.cvtColor(imagem, cv2.COLOR_BGR2LAB).astype(np.float32)
    fundo = cor_do_fundo(lab)
    croma_do_fundo = float(np.hypot(fundo[1] - _CENTRO_DO_LAB, fundo[2] - _CENTRO_DO_LAB))
    if croma_do_fundo > config.visao_croma_min:
        mascara = _mascara_em_fundo_colorido(lab, fundo)
    else:
        mascara = _mascara_em_fundo_neutro(imagem)
    ys, xs = np.nonzero(mascara)
    if len(xs) == 0:
        return None
    envoltoria = cv2.convexHull(np.stack([xs, ys], axis=1).astype(np.int32))
    if cv2.contourArea(envoltoria) < config.visao_area_minima * area_da_imagem:
        return None
    inicial = _quatro_lados(envoltoria.astype(np.int32))
    if inicial is None:
        return None
    return _ajustar_lados(envoltoria.astype(np.int32), inicial) or inicial


def encolher(cantos: Cantos, margem: float) -> Cantos:
    """Quadrilatero interno, afastado `margem` (fracao do lado) de cada borda.

    O afastamento e feito no plano do tabuleiro, por isso respeita a perspectiva.
    """
    homografia = cv2.getPerspectiveTransform(_matriz(_QUADRADO_UNITARIO), _matriz(cantos))
    internos = np.array(
        [[[margem, margem], [1 - margem, margem], [1 - margem, 1 - margem], [margem, 1 - margem]]],
        dtype=np.float32,
    )
    projetados = cv2.perspectiveTransform(internos, homografia)
    return _para_cantos(projetados.reshape(4, 2).astype(np.float32))


def localizar_tabuleiro(imagem: Imagem) -> Cantos | None:
    """Cantos da area de jogo (as 64 casas), ou None se o tabuleiro nao foi achado."""
    moldura = localizar_moldura(imagem)
    if moldura is None:
        return None
    return encolher(moldura, obter_config().visao_margem_da_moldura)


def retificar(imagem: Imagem, cantos: Cantos) -> Imagem:
    """Vista de topo da area de jogo, quadrada, com `visao_lado_retificado` pixels de lado."""
    lado = obter_config().visao_lado_retificado
    destino = _matriz(tuple((x * lado, y * lado) for x, y in _QUADRADO_UNITARIO))
    homografia = cv2.getPerspectiveTransform(_matriz(cantos), destino)
    retificada: Imagem = cv2.warpPerspective(imagem, homografia, (lado, lado)).astype(np.uint8)
    return retificada


def girar(cantos: Cantos) -> Cantos:
    """Mesmos cantos, comecando pelo seguinte: gira a imagem retificada em 90 graus."""
    return (cantos[1], cantos[2], cantos[3], cantos[0])


def recorte_da_casa[T: np.generic](
    retificada: NDArray[T], linha: int, coluna: int, fracao: float = 1.0
) -> NDArray[T]:
    """Quadrado central da casa na linha e coluna da imagem, com `fracao` do lado dela.

    Serve para a imagem retificada e para qualquer mapa do mesmo tamanho (croma, etc.).
    """
    passo = retificada.shape[0] / LADO
    folga = passo * (1 - fracao) / 2
    y0, y1 = round(linha * passo + folga), round((linha + 1) * passo - folga)
    x0, x1 = round(coluna * passo + folga), round((coluna + 1) * passo - folga)
    return retificada[y0:y1, x0:x1]


def espelhar(cantos: Cantos) -> Cantos:
    """Mesmos cantos, em ordem invertida: transpoe a imagem retificada.

    A transposicao troca linhas por colunas e mantem cada casa escura sobre uma casa
    escura. Serve para ler um tabuleiro montado com a casa clara no canto inferior
    esquerdo de cada jogador.
    """
    return (cantos[0], cantos[3], cantos[2], cantos[1])


def canto_inferior_esquerdo_e_escuro(retificada: Imagem) -> bool:
    """Diz se a diagonal que sai do canto inferior esquerdo e a das casas escuras.

    Compara o croma medio das casas das duas paridades. Funciona com pecas em cima,
    porque as casas claras nunca recebem peca e continuam sem cor.
    """
    fracao = obter_config().visao_fracao_do_disco
    mapa = croma(retificada)
    somas = [0.0, 0.0]
    for linha in range(LADO):
        for coluna in range(LADO):
            recorte = recorte_da_casa(mapa, linha, coluna, fracao)
            somas[(linha + coluna) % 2] += float(np.median(recorte))
    return somas[(LADO - 1) % 2] > somas[LADO % 2]


def orientar(imagem: Imagem, cantos: Cantos) -> Cantos:
    """Cantos reordenados para que o canto inferior esquerdo da retificada seja casa escura.

    Sobram duas orientacoes validas, giradas 180 graus uma da outra; qual delas e a
    certa depende de que lado estao as brancas (`posicao_na_imagem`).
    """
    if canto_inferior_esquerdo_e_escuro(retificar(imagem, cantos)):
        return cantos
    return girar(cantos)


def posicao_na_imagem(casa: Casa, lado_das_brancas: LadoDasBrancas) -> tuple[int, int]:
    """Linha e coluna, na imagem retificada, da casa escura de indice `casa`.

    Com as brancas embaixo, `a1` fica no canto inferior esquerdo. Com as brancas em
    cima, a imagem esta girada 180 graus e `a1` fica no canto superior direito.
    """
    linha, coluna = linha_coluna(casa)
    if lado_das_brancas is LadoDasBrancas.BAIXO:
        return LADO - 1 - linha, coluna
    return linha, LADO - 1 - coluna
