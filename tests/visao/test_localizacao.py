"""Testes da localizacao do tabuleiro, da retificacao e da orientacao."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from apoio.cena import ALTURA, CANTOS_PADRAO, LARGURA, desenhar
from dama.config import obter_config
from dama.regras.tabuleiro import LADO, casa, posicao_inicial, tabuleiro_vazio
from dama.visao.localizacao import (
    canto_inferior_esquerdo_e_escuro,
    croma,
    encolher,
    girar,
    localizar_tabuleiro,
    ordenar_cantos,
    orientar,
    posicao_na_imagem,
    recorte_da_casa,
    reduzir,
    retificar,
)
from dama.visao.tipos import Cantos, Imagem, LadoDasBrancas

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tabuleiro"
TOLERANCIA_SINTETICA = 6.0
TOLERANCIA_REAL = 0.02


def _foto(nome: str) -> Imagem:
    """Foto real do tabuleiro, ja reduzida ao tamanho de processamento."""
    imagem = cv2.imread(str(FIXTURES / nome))
    assert imagem is not None
    return reduzir(imagem.astype(np.uint8))


def _maior_desvio(achados: Cantos, esperados: Cantos) -> float:
    """Maior distancia, em pixels, entre um canto achado e o esperado mais proximo."""
    return max(min(float(np.hypot(x - ex, y - ey)) for ex, ey in esperados) for x, y in achados)


def _casas_no_padrao(retificada: Imagem) -> int:
    """Quantas das 64 casas tem a cor esperada pelo padrao de xadrez.

    Com o canto inferior esquerdo escuro, as casas dessa paridade devem ser coloridas
    e as outras, nao.
    """
    config = obter_config()
    mapa = croma(retificada)
    certas = 0
    for linha in range(LADO):
        for coluna in range(LADO):
            colorida = float(np.median(recorte_da_casa(mapa, linha, coluna, 0.5)))
            escura = (linha + coluna) % 2 == (LADO - 1) % 2
            certas += (colorida > config.visao_croma_min) == escura
    return certas


def test_ordenar_cantos_comeca_no_superior_esquerdo_e_segue_o_relogio() -> None:
    """Quatro pontos embaralhados voltam na ordem padrao dos cantos."""
    embaralhados = np.array([[90, 80], [10, 12], [12, 85], [88, 9]], dtype=np.float32)
    assert ordenar_cantos(embaralhados) == ((10, 12), (88, 9), (90, 80), (12, 85))


def test_encolher_respeita_a_perspectiva() -> None:
    """Encolher um quadrado afasta cada canto pela mesma fracao do lado."""
    quadrado: Cantos = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))
    interno = encolher(quadrado, 0.1)
    assert _maior_desvio(interno, ((10, 10), (90, 10), (90, 90), (10, 90))) < 1e-3


@pytest.mark.parametrize("cheio", [False, True])
def test_localiza_o_tabuleiro_sintetico(cheio: bool) -> None:
    """Os cantos automaticos caem perto dos verdadeiros, com ou sem pecas em cima."""
    tab = posicao_inicial() if cheio else tuple(tabuleiro_vazio())
    achados = localizar_tabuleiro(desenhar(tab))
    assert achados is not None
    assert _maior_desvio(achados, CANTOS_PADRAO) < TOLERANCIA_SINTETICA


def test_mesa_vazia_nao_tem_tabuleiro() -> None:
    """Numa imagem so com a mesa, nenhum tabuleiro e encontrado."""
    mesa = np.full((ALTURA, LARGURA, 3), 205, dtype=np.uint8)
    assert localizar_tabuleiro(mesa) is None


@pytest.mark.parametrize(
    ("nome", "esperados", "minimo_no_padrao"),
    [
        (
            "vazio_inclinado.webp",
            ((40, 336), (1028, 204), (1081, 1342), (58, 1273)),
            64,
        ),
        (
            "vazio_com_medidas.webp",
            ((140, 530), (682, 465), (681, 1117), (121, 1053)),
            58,
        ),
    ],
)
def test_localiza_o_tabuleiro_nas_fotos_reais(
    nome: str, esperados: Cantos, minimo_no_padrao: int
) -> None:
    """Nas fotos do tabuleiro real, os cantos batem com os conferidos a olho.

    Os cantos esperados foram conferidos desenhando a grade sobre a foto retificada.
    Alem disso, a grade resultante precisa cair sobre as casas: quase todas as 64
    tem a cor prevista pelo padrao de xadrez. A segunda foto tem marcas de medida
    desenhadas por cima, que cobrem algumas casas.
    """
    imagem = _foto(nome)
    achados = localizar_tabuleiro(imagem)
    assert achados is not None
    assert _maior_desvio(achados, esperados) < TOLERANCIA_REAL * imagem.shape[1]
    retificada = retificar(imagem, orientar(imagem, achados))
    assert _casas_no_padrao(retificada) >= minimo_no_padrao


def test_localiza_o_tabuleiro_sobre_fundo_colorido() -> None:
    """Na foto real sobre a colcha vermelha estampada, com as 24 pecas, os cantos saem certos.

    Os cantos esperados foram conferidos olhando a foto retificada.
    """
    imagem = _foto("inicial_espelhada_em_fundo_vermelho.jpg")
    achados = localizar_tabuleiro(imagem)
    assert achados is not None
    esperados: Cantos = ((72, 230), (677, 258), (667, 877), (31, 850))
    assert _maior_desvio(achados, esperados) < TOLERANCIA_REAL * imagem.shape[1]


def test_fundo_colorido_sem_tabuleiro_nao_tem_cantos() -> None:
    """Numa imagem so com um fundo colorido, nenhum tabuleiro e encontrado."""
    toalha = np.full((ALTURA, LARGURA, 3), (60, 70, 190), dtype=np.uint8)
    assert localizar_tabuleiro(toalha) is None


def test_retificar_devolve_quadrado_do_tamanho_configurado() -> None:
    """A vista de topo tem o lado definido na configuracao."""
    lado = obter_config().visao_lado_retificado
    retificada = retificar(desenhar(posicao_inicial()), CANTOS_PADRAO)
    assert retificada.shape == (lado, lado, 3)


def test_orientar_poe_casa_escura_no_canto_inferior_esquerdo() -> None:
    """Cantos dados com um quarto de volta a mais sao corrigidos pela orientacao."""
    imagem = desenhar(posicao_inicial())
    assert canto_inferior_esquerdo_e_escuro(retificar(imagem, CANTOS_PADRAO))
    girados = girar(CANTOS_PADRAO)
    assert not canto_inferior_esquerdo_e_escuro(retificar(imagem, girados))
    assert canto_inferior_esquerdo_e_escuro(retificar(imagem, orientar(imagem, girados)))


def test_orientacao_nas_fotos_reais_acha_os_cantos_escuros() -> None:
    """Nas duas fotos reais, a orientacao deixa casa escura no canto inferior esquerdo."""
    for nome in ("vazio_inclinado.webp", "vazio_com_medidas.webp"):
        imagem = _foto(nome)
        achados = localizar_tabuleiro(imagem)
        assert achados is not None
        retificada = retificar(imagem, orientar(imagem, achados))
        assert canto_inferior_esquerdo_e_escuro(retificada)


def test_posicao_na_imagem_segue_o_lado_das_brancas() -> None:
    """a1 fica embaixo a esquerda com as brancas embaixo, e em cima a direita se nao."""
    assert posicao_na_imagem(casa("a1"), LadoDasBrancas.BAIXO) == (7, 0)
    assert posicao_na_imagem(casa("h8"), LadoDasBrancas.BAIXO) == (0, 7)
    assert posicao_na_imagem(casa("a1"), LadoDasBrancas.CIMA) == (0, 7)
    assert posicao_na_imagem(casa("h8"), LadoDasBrancas.CIMA) == (7, 0)
