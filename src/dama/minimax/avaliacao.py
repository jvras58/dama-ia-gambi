"""Funcao de avaliacao estatica, em centesimos de pedra.

Considera material, avanco das pedras, controle do centro, mobilidade e pecas ameacadas.
O resultado e sempre do ponto de vista do lado da vez.
"""

from ..regras.tabuleiro import COLUNA, FRENTE, LINHA, N_CASAS, RAIOS
from ..regras.tipos import BRANCA, PEDRA, PRETA, Tabuleiro

VALOR_PEDRA = 100
VALOR_DAMA = 300
PESO_AVANCO = 3  # por fileira avancada
PESO_CENTRO = 5  # pedra numa casa central
PESO_MOBILIDADE = 2  # por movimento simples disponivel
PESO_AMEACA = 15  # por peca que o adversario pode capturar com um salto curto
PESO_ULTIMA_FILEIRA = 6  # pedra guardando a propria primeira fileira

_CENTRO = frozenset(i for i in range(N_CASAS) if 2 <= COLUNA[i] <= 5 and 2 <= LINHA[i] <= 5)
# Pares (direcao do atacante, direcao do pouso): o pouso fica do lado oposto ao atacante.
_OPOSTA = (3, 2, 1, 0)


def _lado(tab: Tabuleiro, cor: int) -> int:
    """Pontuacao de um lado, sem descontar a do outro."""
    total = 0
    frente = FRENTE[cor]
    base = 0 if cor == BRANCA else 7
    for i in range(N_CASAS):
        peca = tab[i] * cor
        if peca <= 0:
            continue
        raios = RAIOS[i]
        if peca == PEDRA:
            avanco = LINHA[i] if cor == BRANCA else 7 - LINHA[i]
            total += VALOR_PEDRA + PESO_AVANCO * avanco
            if i in _CENTRO:
                total += PESO_CENTRO
            if LINHA[i] == base:
                total += PESO_ULTIMA_FILEIRA
            for d in frente:
                raio = raios[d]
                if raio and tab[raio[0]] == 0:
                    total += PESO_MOBILIDADE
        else:
            total += VALOR_DAMA
            for raio in raios:
                for alvo in raio:
                    if tab[alvo] != 0:
                        break
                    total += PESO_MOBILIDADE
        # Ameacada: inimigo encostado numa diagonal e casa vazia do lado oposto.
        for d in range(4):
            raio = raios[d]
            oposto = raios[_OPOSTA[d]]
            if raio and oposto and tab[raio[0]] * cor < 0 and tab[oposto[0]] == 0:
                total -= PESO_AMEACA
                break
    return total


def avaliar(tab: Tabuleiro, vez: int) -> int:
    """Pontuacao da posicao para o lado `vez` (positivo = bom para quem joga)."""
    return (_lado(tab, BRANCA) - _lado(tab, PRETA)) * (1 if vez == BRANCA else -1)
