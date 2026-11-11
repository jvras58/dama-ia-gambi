"""Tipos basicos do jogo.

O tabuleiro tem 32 casas escuras, numeradas de 0 a 31. A linha 0 fica do lado das
brancas; `a1` (linha 0, coluna 0) e casa escura e tem indice 0.

Cada casa guarda um inteiro:
    0  vazia
    1  pedra branca     2  dama branca
   -1  pedra preta     -2  dama preta
"""

from dataclasses import dataclass

VAZIA = 0
PEDRA = 1
DAMA = 2

BRANCA = 1
PRETA = -1

Tabuleiro = tuple[int, ...]

NOME_COR = {BRANCA: "brancas", PRETA: "pretas"}


def cor_de(peca: int) -> int:
    """Cor da peca (BRANCA ou PRETA), ou 0 se a casa esta vazia."""
    return (peca > 0) - (peca < 0)


def eh_dama(peca: int) -> bool:
    return peca == DAMA or peca == -DAMA


@dataclass(frozen=True, slots=True)
class Lance:
    """Um lance completo de um lado.

    `caminho` sao as casas onde a peca pousa, em ordem (uma so para lance simples).
    `capturas` sao as casas das pecas capturadas, na ordem em que foram saltadas.
    """

    origem: int
    caminho: tuple[int, ...]
    capturas: tuple[int, ...] = ()

    @property
    def destino(self) -> int:
        return self.caminho[-1]

    @property
    def eh_captura(self) -> bool:
        return bool(self.capturas)
