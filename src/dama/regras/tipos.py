"""Tipos basicos do jogo.

O tabuleiro tem 32 casas escuras, numeradas de 0 a 31. A linha 0 fica do lado das
brancas; `a1` (linha 0, coluna 0) e casa escura e tem indice 0.

Cada casa guarda um inteiro (`Peca`):
    0  vazia
    1  pedra branca     2  dama branca
   -1  pedra preta     -2  dama preta

`Cor` e BRANCA (1) ou PRETA (-1), e `Casa` e um indice de 0 a 31. A codificacao em
inteiros e parte da representacao (a busca multiplica peca por cor), por isso fica
aqui e nao na configuracao.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

type Peca = int
type Cor = int
type Casa = int
type Tabuleiro = tuple[Peca, ...]

VAZIA: Final[Peca] = 0
PEDRA: Final[Peca] = 1
DAMA: Final[Peca] = 2

BRANCA: Final[Cor] = 1
PRETA: Final[Cor] = -1
CORES: Final[tuple[Cor, Cor]] = (BRANCA, PRETA)


class Lado(StrEnum):
    """Nome de cada lado, como aparece em textos e arquivos."""

    BRANCAS = "brancas"
    PRETAS = "pretas"


class Resultado(StrEnum):
    """Como uma partida termina."""

    BRANCAS = "brancas"
    PRETAS = "pretas"
    EMPATE = "empate"


NOME_COR: Final[Mapping[Cor, Lado]] = {BRANCA: Lado.BRANCAS, PRETA: Lado.PRETAS}
COR_DO_LADO: Final[Mapping[Lado, Cor]] = {Lado.BRANCAS: BRANCA, Lado.PRETAS: PRETA}
VITORIA_DE: Final[Mapping[Cor, Resultado]] = {
    BRANCA: Resultado.BRANCAS,
    PRETA: Resultado.PRETAS,
}


def cor_de(peca: Peca) -> Cor:
    """Cor da peca (BRANCA ou PRETA), ou 0 se a casa esta vazia."""
    return (peca > 0) - (peca < 0)


def eh_dama(peca: Peca) -> bool:
    """Diz se a peca e uma dama, de qualquer cor."""
    return peca == DAMA or peca == -DAMA


@dataclass(frozen=True, slots=True)
class Lance:
    """Um lance completo de um lado.

    `caminho` sao as casas onde a peca pousa, em ordem (uma so para lance simples).
    `capturas` sao as casas das pecas capturadas, na ordem em que foram saltadas.
    """

    origem: Casa
    caminho: tuple[Casa, ...]
    capturas: tuple[Casa, ...] = ()

    @property
    def destino(self) -> Casa:
        """Casa onde a peca termina o lance."""
        return self.caminho[-1]

    @property
    def eh_captura(self) -> bool:
        """Diz se o lance captura ao menos uma peca."""
        return bool(self.capturas)
