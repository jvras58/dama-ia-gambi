"""Gerador de fotos sinteticas do tabuleiro, para testar a visao sem camera.

Desenha o tabuleiro de referencia visto de cima (casas marrons e brancas, moldura fina,
pecas pretas e brancas) e o projeta em perspectiva sobre uma mesa clara, com ruido. As
cores imitam as fotos reais de `tests/fixtures/tabuleiro/`.
"""

from typing import Final

import cv2
import numpy as np

from dama.regras.tabuleiro import LADO, N_CASAS
from dama.regras.tipos import Tabuleiro
from dama.visao.localizacao import posicao_na_imagem
from dama.visao.tipos import Cantos, Imagem, LadoDasBrancas

type Bgr = tuple[int, int, int]

LARGURA: Final[int] = 1280
ALTURA: Final[int] = 960
CANTOS_PADRAO: Final[Cantos] = ((330.0, 150.0), (960.0, 190.0), (1010.0, 820.0), (270.0, 780.0))

_PASSO: Final[int] = 100
_MARGEM: Final[int] = 14
_MOLDURA: Final[int] = 10
_MESA: Final[Bgr] = (208, 208, 206)
_CASA_ESCURA: Final[Bgr] = (88, 104, 150)
_CASA_CLARA: Final[Bgr] = (226, 226, 224)
_PECA_BRANCA: Final[Bgr] = (236, 238, 238)
_PECA_PRETA: Final[Bgr] = (38, 36, 36)
_BORDA_DA_PECA: Final[Bgr] = (120, 120, 120)
_RAIO_DA_PECA: Final[int] = 38
_RUIDO: Final[float] = 4.0


def _vista_de_topo(tab: Tabuleiro, lado_das_brancas: LadoDasBrancas, reflexo: bool) -> Imagem:
    """Tabuleiro visto de cima, com moldura, margem branca e pecas."""
    lado = LADO * _PASSO + 2 * _MARGEM
    imagem = np.full((lado, lado, 3), _CASA_CLARA, dtype=np.uint8)
    cv2.rectangle(imagem, (0, 0), (lado - 1, lado - 1), _CASA_ESCURA, _MOLDURA)
    for linha in range(LADO):
        for coluna in range(LADO):
            escura = (linha + coluna) % 2 == (LADO - 1) % 2
            x0, y0 = _MARGEM + coluna * _PASSO, _MARGEM + linha * _PASSO
            cor = _CASA_ESCURA if escura else _CASA_CLARA
            cv2.rectangle(imagem, (x0, y0), (x0 + _PASSO - 1, y0 + _PASSO - 1), cor, -1)
    for casa in range(N_CASAS):
        linha, coluna = posicao_na_imagem(casa, lado_das_brancas)
        centro = (_MARGEM + coluna * _PASSO + _PASSO // 2, _MARGEM + linha * _PASSO + _PASSO // 2)
        if tab[casa] != 0:
            cor = _PECA_BRANCA if tab[casa] > 0 else _PECA_PRETA
            cv2.circle(imagem, centro, _RAIO_DA_PECA, cor, -1, cv2.LINE_AA)
            cv2.circle(imagem, centro, _RAIO_DA_PECA, _BORDA_DA_PECA, 2, cv2.LINE_AA)
        elif reflexo and casa % 5 == 0:
            cv2.circle(imagem, (centro[0] - 12, centro[1] - 10), 14, (255, 255, 255), -1)
    return imagem


def desenhar(
    tab: Tabuleiro,
    lado_das_brancas: LadoDasBrancas = LadoDasBrancas.BAIXO,
    cantos: Cantos = CANTOS_PADRAO,
    brilho: float = 1.0,
    reflexo: bool = False,
    semente: int = 0,
) -> Imagem:
    """Foto sintetica do tabuleiro `tab`, com a area de jogo nos `cantos` dados.

    `brilho` multiplica a luz da cena, `reflexo` poe manchas estouradas em algumas
    casas vazias, e `semente` fixa o ruido.
    """
    topo = _vista_de_topo(tab, lado_das_brancas, reflexo)
    lado = topo.shape[0]
    fim = lado - _MARGEM
    origem = np.array(
        [[_MARGEM, _MARGEM], [fim, _MARGEM], [fim, fim], [_MARGEM, fim]], dtype=np.float32
    )
    homografia = cv2.getPerspectiveTransform(origem, np.array(cantos, dtype=np.float32))
    cena = np.full((ALTURA, LARGURA, 3), _MESA, dtype=np.uint8)
    cv2.warpPerspective(
        topo, homografia, (LARGURA, ALTURA), dst=cena, borderMode=cv2.BORDER_TRANSPARENT
    )
    gerador = np.random.default_rng(semente)
    ruidosa = cena.astype(np.float64) * brilho + gerador.normal(0.0, _RUIDO, cena.shape)
    return np.clip(ruidosa, 0, 255).astype(np.uint8)


def como_jpeg(imagem: Imagem) -> bytes:
    """Codifica a imagem em JPEG, como o telefone envia."""
    ok, dados = cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, 80])
    assert ok
    return dados.tobytes()
