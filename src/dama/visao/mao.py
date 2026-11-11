"""Deteccao de mao sobre o tabuleiro com o MediaPipe Hand Landmarker.

Enquanto ha uma mao sobre o tabuleiro, a leitura das casas nao e confiavel: a mao cobre
pecas e projeta sombra. O pipeline usa este modulo para suspender a leitura.

O modelo (`hand_landmarker.task`, cerca de 7,8 MB) nao vem com o projeto: e baixado por
`dama baixar-modelo` para a pasta `modelos/`. Sem ele, o detector fica indisponivel e o
pipeline segue sem o bloqueio por mao.
"""

from pathlib import Path
from typing import Final

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

from dama.config import obter_config
from dama.visao.tipos import Cantos, Imagem

NOME_DO_MODELO: Final[str] = "hand_landmarker.task"
URL_DO_MODELO: Final[str] = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/"
    "float16/1/hand_landmarker.task"
)
_MILISSEGUNDOS: Final[int] = 1000


def caminho_do_modelo() -> Path:
    """Onde o modelo de mao deve estar no disco."""
    return obter_config().pasta_modelos / NOME_DO_MODELO


def modelo_disponivel() -> bool:
    """Diz se o modelo de mao ja foi baixado."""
    return caminho_do_modelo().is_file()


def dilatar(cantos: Cantos, fracao: float) -> Cantos:
    """Quadrilatero aumentado em `fracao` a partir do proprio centro."""
    pontos = np.array(cantos, dtype=np.float64)
    centro = pontos.mean(axis=0)
    maiores = centro + (pontos - centro) * (1 + fracao)
    p = [(float(x), float(y)) for x, y in maiores]
    return (p[0], p[1], p[2], p[3])


def ponto_dentro(ponto: tuple[float, float], cantos: Cantos) -> bool:
    """Diz se o ponto esta dentro do quadrilatero (ou sobre a borda)."""
    contorno = np.array(cantos, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.pointPolygonTest(contorno, ponto, False) >= 0


class DetectorDeMao:
    """Detecta maos em frames sucessivos de video.

    O Hand Landmarker roda em modo video, que exige um carimbo de tempo crescente a
    cada frame; por isso o detector guarda o ultimo carimbo usado.
    """

    def __init__(self, modelo: Path | None = None) -> None:
        """Carrega o modelo; levanta FileNotFoundError se ele nao foi baixado."""
        config = obter_config()
        caminho = modelo or caminho_do_modelo()
        if not caminho.is_file():
            raise FileNotFoundError(f"modelo de mao nao encontrado em {caminho}")
        opcoes = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=caminho.read_bytes()),
            running_mode=RunningMode.VIDEO,
            num_hands=config.mao_maximo,
            min_hand_detection_confidence=config.mao_confianca_min,
        )
        self._detector = HandLandmarker.create_from_options(opcoes)
        self._ultimo_carimbo_ms: int = 0

    def pontos(self, imagem: Imagem, instante_s: float) -> list[tuple[float, float]]:
        """Pontos de todas as maos vistas no frame, em pixels da imagem."""
        carimbo = max(self._ultimo_carimbo_ms + 1, round(instante_s * _MILISSEGUNDOS))
        self._ultimo_carimbo_ms = carimbo
        rgb = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)
        quadro = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        resultado = self._detector.detect_for_video(quadro, carimbo)
        altura, largura = imagem.shape[:2]
        return [
            (ponto.x * largura, ponto.y * altura)
            for mao in resultado.hand_landmarks
            for ponto in mao
        ]

    def ha_mao_sobre(self, imagem: Imagem, cantos: Cantos, instante_s: float) -> bool:
        """Diz se algum ponto de alguma mao esta sobre o tabuleiro.

        O tabuleiro e aumentado em `mao_margem`, para pegar a mao que ainda esta
        chegando ou saindo.
        """
        area = dilatar(cantos, obter_config().mao_margem)
        return any(ponto_dentro(ponto, area) for ponto in self.pontos(imagem, instante_s))

    def fechar(self) -> None:
        """Libera o modelo."""
        self._detector.close()
