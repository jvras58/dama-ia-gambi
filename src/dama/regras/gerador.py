"""Geracao de lances legais das damas brasileiras.

- Pedra anda uma casa para frente; captura para frente e para tras.
- Dama anda e captura a qualquer distancia na diagonal.
- Captura e obrigatoria, e vale a lei da maioria (captura-se o maximo de pecas).
- Pecas capturadas so saem do tabuleiro ao fim do lance e nao podem ser saltadas duas vezes.
"""

from .tabuleiro import FRENTE, LINHA, N_CASAS, RAIOS
from .tipos import BRANCA, DAMA, PEDRA, Lance, Tabuleiro, cor_de


def gerar_lances(tab: Tabuleiro, vez: int) -> list[Lance]:
    """Todos os lances legais do lado `vez`, em ordem estavel."""
    capturas = _gerar_capturas(tab, vez)
    if capturas:
        maior = max(len(lance.capturas) for lance in capturas)
        return [lance for lance in capturas if len(lance.capturas) == maior]
    return _gerar_simples(tab, vez)


def _gerar_simples(tab: Tabuleiro, vez: int) -> list[Lance]:
    lances = []
    frente = FRENTE[vez]
    for i in range(N_CASAS):
        peca = tab[i]
        if peca * vez <= 0:
            continue
        raios = RAIOS[i]
        if peca * vez == PEDRA:
            for d in frente:
                raio = raios[d]
                if raio and tab[raio[0]] == 0:
                    lances.append(Lance(i, (raio[0],)))
        else:
            for raio in raios:
                for alvo in raio:
                    if tab[alvo] != 0:
                        break
                    lances.append(Lance(i, (alvo,)))
    return lances


def _gerar_capturas(tab: Tabuleiro, vez: int) -> list[Lance]:
    lances: list[Lance] = []
    for i in range(N_CASAS):
        peca = tab[i]
        if peca * vez <= 0:
            continue
        if peca * vez == PEDRA:
            _capturas_pedra(tab, vez, i, i, (), (), lances)
        else:
            _capturas_dama(tab, vez, i, i, (), (), lances)
    return lances


def _capturas_pedra(
    tab: Tabuleiro,
    vez: int,
    origem: int,
    pos: int,
    caminho: tuple[int, ...],
    capturadas: tuple[int, ...],
    saida: list[Lance],
) -> None:
    continuou = False
    for raio in RAIOS[pos]:
        if len(raio) < 2:
            continue
        alvo, pouso = raio[0], raio[1]
        if tab[alvo] * vez >= 0 or alvo in capturadas:
            continue
        # A casa de origem conta como vazia: a peca ja saiu de la.
        if tab[pouso] != 0 and pouso != origem:
            continue
        continuou = True
        _capturas_pedra(tab, vez, origem, pouso, (*caminho, pouso), (*capturadas, alvo), saida)
    if not continuou and capturadas:
        saida.append(Lance(origem, caminho, capturadas))


def _capturas_dama(
    tab: Tabuleiro,
    vez: int,
    origem: int,
    pos: int,
    caminho: tuple[int, ...],
    capturadas: tuple[int, ...],
    saida: list[Lance],
) -> None:
    continuou = False
    for raio in RAIOS[pos]:
        alvo = -1
        for k, c in enumerate(raio):
            if tab[c] == 0 or c == origem:
                continue
            # Primeira peca no caminho: so serve se for inimiga ainda nao capturada.
            if tab[c] * vez < 0 and c not in capturadas:
                alvo = k
            break
        if alvo < 0:
            continue
        for pouso in raio[alvo + 1 :]:
            if tab[pouso] != 0 and pouso != origem:
                break
            continuou = True
            _capturas_dama(
                tab, vez, origem, pouso, (*caminho, pouso), (*capturadas, raio[alvo]), saida
            )
    if not continuou and capturadas:
        saida.append(Lance(origem, caminho, capturadas))


def aplicar(tab: Tabuleiro, lance: Lance) -> Tabuleiro:
    """Devolve o tabuleiro depois do lance. Nao verifica se o lance e legal."""
    novo = list(tab)
    peca = novo[lance.origem]
    novo[lance.origem] = 0
    for c in lance.capturas:
        novo[c] = 0
    destino = lance.destino
    if peca == PEDRA and LINHA[destino] == 7:
        peca = DAMA
    elif peca == -PEDRA and LINHA[destino] == 0:
        peca = -DAMA
    novo[destino] = peca
    return tuple(novo)


def promove(tab: Tabuleiro, lance: Lance) -> bool:
    """O lance termina com uma pedra virando dama?"""
    peca = tab[lance.origem]
    ultima = 7 if cor_de(peca) == BRANCA else 0
    return abs(peca) == PEDRA and LINHA[lance.destino] == ultima
