"""Representacao do tabuleiro, coordenadas, notacao e posicao inicial."""

from .tipos import BRANCA, DAMA, PEDRA, PRETA, VAZIA, Lance, Tabuleiro

N_CASAS = 32
COLUNAS = "abcdefgh"

# Direcoes diagonais como (delta_linha, delta_coluna).
DIRECOES = ((1, 1), (1, -1), (-1, 1), (-1, -1))
# Indices em DIRECOES para onde cada cor avanca.
FRENTE = {BRANCA: (0, 1), PRETA: (2, 3)}


def indice(linha: int, coluna: int) -> int:
    """Indice (0-31) da casa escura em (linha, coluna)."""
    if not (0 <= linha < 8 and 0 <= coluna < 8) or (linha + coluna) % 2:
        raise ValueError(f"({linha}, {coluna}) nao e uma casa escura do tabuleiro")
    return linha * 4 + coluna // 2


def linha_coluna(i: int) -> tuple[int, int]:
    linha = i // 4
    return linha, (i % 4) * 2 + (linha % 2)


def _calcular_raios() -> tuple[tuple[tuple[int, ...], ...], ...]:
    raios = []
    for i in range(N_CASAS):
        linha, coluna = linha_coluna(i)
        por_direcao = []
        for dl, dc in DIRECOES:
            raio = []
            lin, col = linha + dl, coluna + dc
            while 0 <= lin < 8 and 0 <= col < 8:
                raio.append(indice(lin, col))
                lin, col = lin + dl, col + dc
            por_direcao.append(tuple(raio))
        raios.append(tuple(por_direcao))
    return tuple(raios)


# RAIOS[casa][direcao] = casas a partir de `casa` naquela diagonal, da mais perto a mais longe.
RAIOS = _calcular_raios()

LINHA = tuple(linha_coluna(i)[0] for i in range(N_CASAS))
COLUNA = tuple(linha_coluna(i)[1] for i in range(N_CASAS))


def posicao_inicial() -> Tabuleiro:
    """12 pedras brancas nas linhas 1-3 e 12 pretas nas linhas 6-8."""
    return tuple([PEDRA] * 12 + [VAZIA] * 8 + [-PEDRA] * 12)


def tabuleiro_vazio() -> list[int]:
    return [VAZIA] * N_CASAS


# --- Notacao ---------------------------------------------------------------


def nome_casa(i: int) -> str:
    linha, coluna = linha_coluna(i)
    return f"{COLUNAS[coluna]}{linha + 1}"


def casa(nome: str) -> int:
    """Converte 'c3' no indice da casa. Levanta ValueError se nao for casa escura."""
    nome = nome.strip().lower()
    if len(nome) != 2 or nome[0] not in COLUNAS or nome[1] not in "12345678":
        raise ValueError(f"casa invalida: {nome!r}")
    return indice(int(nome[1]) - 1, COLUNAS.index(nome[0]))


def notacao(lance: Lance) -> str:
    """'c3-d4' para lance simples, 'c3xe5xg7' para captura."""
    sep = "x" if lance.eh_captura else "-"
    return sep.join(nome_casa(c) for c in (lance.origem, *lance.caminho))


_SIMBOLOS = {VAZIA: ".", PEDRA: "b", DAMA: "B", -PEDRA: "p", -DAMA: "P"}
_PECAS = {simbolo: peca for peca, simbolo in _SIMBOLOS.items()}


def para_texto(tab: Tabuleiro) -> str:
    """Grade 8x8 com a linha 8 em cima.

    b/B = pedra/dama branca, p/P = pedra/dama preta, '.' = casa escura vazia,
    espaco = casa clara.
    """
    linhas = []
    for linha in range(7, -1, -1):
        celulas = []
        for coluna in range(8):
            if (linha + coluna) % 2:
                celulas.append(" ")
            else:
                celulas.append(_SIMBOLOS[tab[indice(linha, coluna)]])
        linhas.append(f"{linha + 1} {' '.join(celulas)}")
    linhas.append("  " + " ".join(COLUNAS))
    return "\n".join(linhas)


def montar(pecas: dict[str, str]) -> Tabuleiro:
    """Monta um tabuleiro a partir de {'c3': 'b', 'e5': 'P', ...}. Util em testes e na edicao."""
    tab = tabuleiro_vazio()
    for nome, simbolo in pecas.items():
        if simbolo not in _PECAS or simbolo == ".":
            raise ValueError(f"peca invalida: {simbolo!r}")
        tab[casa(nome)] = _PECAS[simbolo]
    return tuple(tab)


def espelhar(tab: Tabuleiro) -> Tabuleiro:
    """Gira o tabuleiro 180 graus e troca as cores."""
    return tuple(-p for p in reversed(tab))
