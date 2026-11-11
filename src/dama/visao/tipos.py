"""Tipos da visao computacional.

Convencoes:
- `Imagem` e uma matriz BGR de 8 bits, como o OpenCV devolve.
- `Ponto` e (x, y) em pixels da imagem, com a origem no canto superior esquerdo.
- `Cantos` sao os quatro cantos de um quadrilatero, sempre na ordem: superior esquerdo,
  superior direito, inferior direito, inferior esquerdo.
"""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

type Imagem = NDArray[np.uint8]
type Ponto = tuple[float, float]
type Cantos = tuple[Ponto, Ponto, Ponto, Ponto]


class Ocupacao(StrEnum):
    """O que a camera ve numa casa escura. Damas nao sao distinguidas de pedras."""

    VAZIA = "vazia"
    BRANCA = "branca"
    PRETA = "preta"


class LadoDasBrancas(StrEnum):
    """Em que borda da imagem retificada fica a primeira fileira das brancas."""

    BAIXO = "baixo"
    CIMA = "cima"


@dataclass(frozen=True, slots=True)
class LeituraCasa:
    """Classificacao de uma casa escura num frame."""

    ocupacao: Ocupacao
    confianca: float
    """De 0 a 1: quao mais perto a casa esta da classe escolhida do que da segunda."""
