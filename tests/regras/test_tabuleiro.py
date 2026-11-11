import pytest

from dama.regras.tabuleiro import (
    RAIOS,
    casa,
    espelhar,
    indice,
    linha_coluna,
    montar,
    nome_casa,
    notacao,
    para_texto,
    posicao_inicial,
)
from dama.regras.tipos import PEDRA, Lance


def test_a1_e_casa_escura_de_indice_zero():
    assert casa("a1") == 0
    assert casa("h8") == 31
    assert nome_casa(0) == "a1"


def test_notacao_de_casa_ida_e_volta():
    for i in range(32):
        assert casa(nome_casa(i)) == i
        assert indice(*linha_coluna(i)) == i


@pytest.mark.parametrize("nome", ["a2", "h1", "i1", "a9", "", "abc"])
def test_casa_clara_ou_invalida_e_recusada(nome):
    with pytest.raises(ValueError):
        casa(nome)


def test_posicao_inicial():
    tab = posicao_inicial()
    assert sum(1 for p in tab if p == PEDRA) == 12
    assert sum(1 for p in tab if p == -PEDRA) == 12
    assert tab[casa("a1")] == PEDRA
    assert tab[casa("h8")] == -PEDRA
    assert all(tab[casa(c)] == 0 for c in ("b4", "d4", "f4", "h4", "a5", "c5", "e5", "g5"))


def test_raios_da_grande_diagonal():
    assert [nome_casa(c) for c in RAIOS[casa("a1")][0]] == [
        "b2", "c3", "d4", "e5", "f6", "g7", "h8",
    ]  # fmt: skip
    assert RAIOS[casa("a1")][1] == ()


def test_notacao_de_lance():
    assert notacao(Lance(casa("c3"), (casa("d4"),))) == "c3-d4"
    captura = Lance(casa("c3"), (casa("e5"), casa("g7")), (casa("d4"), casa("f6")))
    assert notacao(captura) == "c3xe5xg7"


def test_texto_do_tabuleiro():
    texto = para_texto(montar({"a1": "b", "h8": "P"}))
    linhas = texto.splitlines()
    assert linhas[0].startswith("8")
    assert linhas[0].rstrip().endswith("P")
    assert linhas[7].startswith("1 b")
    assert linhas[8].split() == list("abcdefgh")


def test_espelhar_duas_vezes_volta_ao_original():
    tab = montar({"c3": "b", "e5": "P", "h2": "B"})
    assert espelhar(espelhar(tab)) == tab
    assert espelhar(posicao_inicial()) == posicao_inicial()
