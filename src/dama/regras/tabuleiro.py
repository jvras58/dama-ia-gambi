"""Representacao do tabuleiro, coordenadas, notacao e posicao inicial.

A geometria (tabuleiro 8x8, 32 casas escuras, 12 pedras por lado) faz parte das regras
e nao e ajustavel; por isso fica aqui, e nao na configuracao.

Tabelas deste modulo:
- `DIRECOES`: as quatro diagonais, como (delta_linha, delta_coluna).
- `FRENTE`: para cada cor, os indices em `DIRECOES` para onde as pedras avancam.
- `LINHA_DE_PROMOCAO` e `LINHA_DE_BASE`: para cada cor, a linha em que a pedra vira
  dama e a linha de onde ela parte.
- `RAIOS[casa][direcao]`: as casas a partir de `casa` naquela diagonal, da mais perto
  para a mais longe.
- `LINHA[casa]` e `COLUNA[casa]`: coordenadas de cada casa.
- `SIMBOLOS`: o caractere que representa cada peca no diagrama em texto.
"""

from collections.abc import Mapping
from typing import Final

from dama.regras.tipos import (
    BRANCA,
    DAMA,
    PEDRA,
    PRETA,
    VAZIA,
    Casa,
    Cor,
    Lance,
    Peca,
    Tabuleiro,
)

type Raio = tuple[Casa, ...]
type Raios = tuple[tuple[Raio, ...], ...]

LADO: Final[int] = 8
ULTIMA_LINHA: Final[int] = LADO - 1
N_CASAS: Final[int] = LADO * LADO // 2
PEDRAS_POR_LADO: Final[int] = 12
COLUNAS: Final[str] = "abcdefgh"
FILEIRAS: Final[str] = "12345678"

DIRECOES: Final[tuple[tuple[int, int], ...]] = ((1, 1), (1, -1), (-1, 1), (-1, -1))
FRENTE: Final[Mapping[Cor, tuple[int, int]]] = {BRANCA: (0, 1), PRETA: (2, 3)}
LINHA_DE_PROMOCAO: Final[Mapping[Cor, int]] = {BRANCA: ULTIMA_LINHA, PRETA: 0}
LINHA_DE_BASE: Final[Mapping[Cor, int]] = {BRANCA: 0, PRETA: ULTIMA_LINHA}


def indice(linha: int, coluna: int) -> Casa:
    """Indice (0-31) da casa escura em (linha, coluna)."""
    if not (0 <= linha < LADO and 0 <= coluna < LADO) or (linha + coluna) % 2:
        raise ValueError(f"({linha}, {coluna}) nao e uma casa escura do tabuleiro")
    return linha * (LADO // 2) + coluna // 2


def linha_coluna(i: Casa) -> tuple[int, int]:
    """Linha e coluna (0-7) da casa de indice `i`."""
    linha = i // (LADO // 2)
    return linha, (i % (LADO // 2)) * 2 + (linha % 2)


def _calcular_raios() -> Raios:
    """Monta a tabela `RAIOS`: para cada casa e direcao, as casas daquela diagonal."""
    raios: list[tuple[Raio, ...]] = []
    for i in range(N_CASAS):
        linha, coluna = linha_coluna(i)
        por_direcao: list[Raio] = []
        for dl, dc in DIRECOES:
            raio: list[Casa] = []
            lin, col = linha + dl, coluna + dc
            while 0 <= lin < LADO and 0 <= col < LADO:
                raio.append(indice(lin, col))
                lin, col = lin + dl, col + dc
            por_direcao.append(tuple(raio))
        raios.append(tuple(por_direcao))
    return tuple(raios)


RAIOS: Final[Raios] = _calcular_raios()
LINHA: Final[tuple[int, ...]] = tuple(linha_coluna(i)[0] for i in range(N_CASAS))
COLUNA: Final[tuple[int, ...]] = tuple(linha_coluna(i)[1] for i in range(N_CASAS))


def posicao_inicial() -> Tabuleiro:
    """12 pedras brancas nas linhas 1-3 e 12 pretas nas linhas 6-8."""
    vazias = N_CASAS - 2 * PEDRAS_POR_LADO
    return tuple([PEDRA] * PEDRAS_POR_LADO + [VAZIA] * vazias + [-PEDRA] * PEDRAS_POR_LADO)


def tabuleiro_vazio() -> list[Peca]:
    """Tabuleiro sem pecas, como lista editavel."""
    return [VAZIA] * N_CASAS


def nome_casa(i: Casa) -> str:
    """Nome da casa de indice `i`, como 'c3'."""
    linha, coluna = linha_coluna(i)
    return f"{COLUNAS[coluna]}{FILEIRAS[linha]}"


def casa(nome: str) -> Casa:
    """Converte 'c3' no indice da casa. Levanta ValueError se nao for casa escura."""
    nome = nome.strip().lower()
    if len(nome) != 2 or nome[0] not in COLUNAS or nome[1] not in FILEIRAS:
        raise ValueError(f"casa invalida: {nome!r}")
    return indice(FILEIRAS.index(nome[1]), COLUNAS.index(nome[0]))


def notacao(lance: Lance) -> str:
    """'c3-d4' para lance simples, 'c3xe5xg7' para captura."""
    sep = "x" if lance.eh_captura else "-"
    return sep.join(nome_casa(c) for c in (lance.origem, *lance.caminho))


SIMBOLO_VAZIA: Final[str] = "."
SIMBOLOS: Final[Mapping[Peca, str]] = {
    VAZIA: SIMBOLO_VAZIA,
    PEDRA: "b",
    DAMA: "B",
    -PEDRA: "p",
    -DAMA: "P",
}
_PECAS: Final[Mapping[str, Peca]] = {simbolo: peca for peca, simbolo in SIMBOLOS.items()}


def para_texto(tab: Tabuleiro) -> str:
    """Grade 8x8 com a linha 8 em cima.

    b/B = pedra/dama branca, p/P = pedra/dama preta, '.' = casa escura vazia,
    espaco = casa clara.
    """
    linhas: list[str] = []
    for linha in range(ULTIMA_LINHA, -1, -1):
        celulas: list[str] = []
        for coluna in range(LADO):
            if (linha + coluna) % 2:
                celulas.append(" ")
            else:
                celulas.append(SIMBOLOS[tab[indice(linha, coluna)]])
        linhas.append(f"{FILEIRAS[linha]} {' '.join(celulas)}")
    linhas.append("  " + " ".join(COLUNAS))
    return "\n".join(linhas)


def montar(pecas: Mapping[str, str]) -> Tabuleiro:
    """Monta um tabuleiro a partir de {'c3': 'b', 'e5': 'P', ...}. Util em testes e na edicao."""
    tab = tabuleiro_vazio()
    for nome, simbolo in pecas.items():
        if simbolo not in _PECAS or simbolo == SIMBOLO_VAZIA:
            raise ValueError(f"peca invalida: {simbolo!r}")
        tab[casa(nome)] = _PECAS[simbolo]
    return tuple(tab)


def espelhar(tab: Tabuleiro) -> Tabuleiro:
    """Gira o tabuleiro 180 graus e troca as cores."""
    return tuple(-p for p in reversed(tab))
