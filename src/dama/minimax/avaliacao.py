"""Funcao de avaliacao estatica, em centesimos de pedra.

Considera material, avanco das pedras, controle do centro, mobilidade e pecas
ameacadas. O resultado e sempre do ponto de vista do lado da vez. Os pesos vem da
configuracao (`DAMA_AVALIACAO_*`).

`_CENTRO` sao as casas centrais: as que ficam fora das duas linhas e colunas de
cada borda. `_OPOSTA[d]` e o indice, em `DIRECOES`, da direcao contraria a `d`.
"""

from typing import Final

from dama.config import Settings, obter_config
from dama.regras.tabuleiro import (
    COLUNA,
    DIRECOES,
    FRENTE,
    LADO,
    LINHA,
    LINHA_DE_BASE,
    N_CASAS,
    RAIOS,
    ULTIMA_LINHA,
)
from dama.regras.tipos import BRANCA, PEDRA, PRETA, VAZIA, Casa, Cor, Tabuleiro

_BORDA: Final[int] = 2
_CENTRO: Final[frozenset[Casa]] = frozenset(
    i
    for i in range(N_CASAS)
    if _BORDA <= COLUNA[i] < LADO - _BORDA and _BORDA <= LINHA[i] < LADO - _BORDA
)
_OPOSTA: Final[tuple[int, ...]] = tuple(DIRECOES.index((-dl, -dc)) for dl, dc in DIRECOES)


def _lado(tab: Tabuleiro, cor: Cor, config: Settings) -> int:
    """Pontuacao de um lado, sem descontar a do outro.

    Uma peca conta como ameacada quando ha um inimigo encostado numa diagonal e a
    casa do lado oposto esta vazia.
    """
    valor_pedra = config.avaliacao_valor_pedra
    valor_dama = config.avaliacao_valor_dama
    peso_avanco = config.avaliacao_peso_avanco
    peso_centro = config.avaliacao_peso_centro
    peso_mobilidade = config.avaliacao_peso_mobilidade
    peso_ameaca = config.avaliacao_peso_ameaca
    peso_ultima_fileira = config.avaliacao_peso_ultima_fileira

    total = 0
    frente = FRENTE[cor]
    base = LINHA_DE_BASE[cor]
    for i in range(N_CASAS):
        peca = tab[i] * cor
        if peca <= 0:
            continue
        raios = RAIOS[i]
        if peca == PEDRA:
            avanco = LINHA[i] if cor == BRANCA else ULTIMA_LINHA - LINHA[i]
            total += valor_pedra + peso_avanco * avanco
            if i in _CENTRO:
                total += peso_centro
            if LINHA[i] == base:
                total += peso_ultima_fileira
            for d in frente:
                raio = raios[d]
                if raio and tab[raio[0]] == VAZIA:
                    total += peso_mobilidade
        else:
            total += valor_dama
            for raio in raios:
                for alvo in raio:
                    if tab[alvo] != VAZIA:
                        break
                    total += peso_mobilidade
        for d, raio in enumerate(raios):
            oposto = raios[_OPOSTA[d]]
            if raio and oposto and tab[raio[0]] * cor < 0 and tab[oposto[0]] == VAZIA:
                total -= peso_ameaca
                break
    return total


def avaliar(tab: Tabuleiro, vez: Cor) -> int:
    """Pontuacao da posicao para o lado `vez` (positivo = bom para quem joga)."""
    config = obter_config()
    return (_lado(tab, BRANCA, config) - _lado(tab, PRETA, config)) * vez
