"""Testes da deteccao de mao.

Os testes que carregam o modelo do MediaPipe sao pulados quando ele nao foi baixado
(`dama baixar-modelo`). Nao ha, ainda, uma foto real com mao sobre o tabuleiro: o caso
positivo so foi conferido com o sensor falso do teste do pipeline.
"""

from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest

from apoio.cena import CANTOS_PADRAO, desenhar
from dama.regras.tabuleiro import posicao_inicial
from dama.visao.localizacao import localizar_tabuleiro, reduzir
from dama.visao.mao import DetectorDeMao, dilatar, modelo_disponivel, ponto_dentro
from dama.visao.tipos import Cantos
from dama.web.servidor import criar_sensor_de_mao

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tabuleiro"
QUADRADO: Cantos = ((100.0, 100.0), (200.0, 100.0), (200.0, 200.0), (100.0, 200.0))
precisa_do_modelo = pytest.mark.skipif(
    not modelo_disponivel(), reason="modelo de mao nao baixado (dama baixar-modelo)"
)


@pytest.fixture(scope="module")
def detector() -> Iterator[DetectorDeMao]:
    """Um detector de mao compartilhado pelos testes do modulo, fechado ao final."""
    detector = DetectorDeMao()
    yield detector
    detector.fechar()


def test_dilatar_aumenta_a_partir_do_centro() -> None:
    """Dilatar em 10% afasta cada canto do centro na mesma proporcao."""
    assert dilatar(QUADRADO, 0.1) == ((95.0, 95.0), (205.0, 95.0), (205.0, 205.0), (95.0, 205.0))


def test_ponto_dentro_do_quadrilatero() -> None:
    """Pontos internos e na borda contam como dentro; os de fora, nao."""
    assert ponto_dentro((150.0, 150.0), QUADRADO)
    assert ponto_dentro((100.0, 150.0), QUADRADO)
    assert not ponto_dentro((99.0, 150.0), QUADRADO)
    assert not ponto_dentro((150.0, 201.0), QUADRADO)


def test_sem_o_modelo_o_detector_avisa(tmp_path: Path) -> None:
    """Pedir o detector com um modelo que nao existe e um erro claro."""
    with pytest.raises(FileNotFoundError):
        DetectorDeMao(tmp_path / "nao_existe.task")


@precisa_do_modelo
def test_tabuleiro_sem_mao_nao_dispara(detector: DetectorDeMao) -> None:
    """Nas fotos reais do tabuleiro vazio, nenhuma mao e detectada."""
    for instante, nome in enumerate(("vazio_inclinado.webp", "vazio_com_medidas.webp"), start=1):
        lida = cv2.imread(str(FIXTURES / nome))
        assert lida is not None
        imagem = reduzir(lida.astype(np.uint8))
        cantos = localizar_tabuleiro(imagem)
        assert cantos is not None
        assert detector.pontos(imagem, float(instante)) == []
        assert not detector.ha_mao_sobre(imagem, cantos, instante + 0.5)


@precisa_do_modelo
def test_pecas_nao_sao_confundidas_com_mao(detector: DetectorDeMao) -> None:
    """Na cena sintetica com as 24 pecas, o detector nao ve mao."""
    imagem = desenhar(posicao_inicial())
    assert not detector.ha_mao_sobre(imagem, CANTOS_PADRAO, 10.0)


@precisa_do_modelo
def test_carimbo_de_tempo_repetido_nao_quebra(detector: DetectorDeMao) -> None:
    """Dois frames com o mesmo instante sao aceitos: o carimbo interno sempre cresce."""
    imagem = desenhar(posicao_inicial())
    assert detector.pontos(imagem, 20.0) == []
    assert detector.pontos(imagem, 20.0) == []
    assert detector.pontos(imagem, 5.0) == []


@precisa_do_modelo
def test_servidor_liga_o_detector_quando_o_modelo_existe() -> None:
    """Com o modelo baixado, o `dama serve` passa a usar o detector de mao."""
    sensor = criar_sensor_de_mao()
    assert isinstance(sensor, DetectorDeMao)
    sensor.fechar()
