import json

import pytest

from dama.regras.gerador import aplicar, gerar_lances
from dama.regras.partida import LIMITE_LANCES_DE_DAMA, LanceIlegal, Partida
from dama.regras.tabuleiro import casa, montar, posicao_inicial
from dama.regras.tipos import BRANCA, DAMA, PRETA, Lance


def test_brancas_comecam_e_a_vez_alterna():
    partida = Partida()
    assert partida.vez == BRANCA
    partida.jogar_texto("c3-d4")
    assert partida.vez == PRETA
    partida.jogar_texto("f6-e5")
    assert partida.vez == BRANCA
    assert [r.texto for r in partida.historico] == ["c3-d4", "f6-e5"]


def test_lance_ilegal_nao_altera_o_estado():
    partida = Partida()
    antes = partida.tab
    with pytest.raises(LanceIlegal):
        partida.jogar_texto("c3-c4")
    with pytest.raises(LanceIlegal):
        partida.jogar(Lance(casa("a1"), (casa("h8"),)))
    assert partida.tab == antes
    assert partida.vez == BRANCA
    assert partida.historico == []


def test_captura_obrigatoria_na_partida():
    partida = Partida()
    for texto in ("c3-d4", "f6-e5"):
        partida.jogar_texto(texto)
    legais = partida.lances_legais()
    assert len(legais) == 1 and legais[0].eh_captura
    with pytest.raises(LanceIlegal):
        partida.jogar_texto("a3-b4")


def test_desfazer_restaura_tudo():
    partida = Partida()
    partida.jogar_texto("c3-d4")
    partida.jogar_texto("f6-e5")
    partida.jogar_texto("d4xf6")
    partida.desfazer()
    assert partida.vez == BRANCA
    assert partida.tab[casa("e5")] != 0
    assert len(partida.historico) == 2
    partida.desfazer()
    partida.desfazer()
    assert partida.tab == posicao_inicial()
    with pytest.raises(LanceIlegal):
        partida.desfazer()


def test_registro_marca_promocao():
    partida = Partida(tab=montar({"a7": "b", "h8": "p"}))
    registro = partida.jogar_texto("a7-b8")
    assert registro.promoveu
    assert partida.tab[casa("b8")] == DAMA


# --- Fim de jogo ---------------------------------------------------------------


def test_lado_sem_pecas_perde():
    partida = Partida(tab=montar({"c3": "b", "d4": "p"}))
    partida.jogar_texto("c3xe5")
    assert partida.resultado() == "brancas"
    assert partida.encerrada()
    assert partida.lances_legais() == []


def test_lado_sem_lances_perde():
    # A pedra preta em a5 esta bloqueada por b4 (e nao pode capturar, pois c3 esta ocupada).
    partida = Partida(tab=montar({"a5": "p", "b4": "b", "c3": "b"}), vez=PRETA)
    assert partida.resultado() == "brancas"


def test_jogo_em_andamento_nao_tem_resultado():
    assert Partida().resultado() is None


def test_empate_por_lances_de_dama():
    partida = Partida(tab=montar({"a1": "B", "h2": "P"}), vez=BRANCA)
    # As damas vao e voltam em diagonais que nao se cruzam.
    ciclo = ["a1-b2", "h2-g1", "b2-a1", "g1-h2"]
    for n in range(LIMITE_LANCES_DE_DAMA):
        assert partida.resultado() is None
        partida.jogar_texto(ciclo[n % 4])
    assert partida.resultado() == "empate"
    assert partida.lances_legais() == []


def test_movimento_de_pedra_zera_o_contador_de_empate():
    partida = Partida(tab=montar({"a1": "B", "h2": "P", "a3": "b"}))
    partida.jogar_texto("a1-b2")
    partida.jogar_texto("h2-g1")
    assert partida.lances_de_dama == 2
    partida.jogar_texto("a3-b4")
    assert partida.lances_de_dama == 0


def test_empate_por_acordo():
    partida = Partida()
    partida.empate_por_acordo = True
    assert partida.resultado() == "empate"


# --- Exportacao ----------------------------------------------------------------


def test_exportar_e_reimportar():
    partida = Partida()
    for texto in ("c3-d4", "f6-e5", "d4xf6", "g7xe5"):
        partida.jogar_texto(texto)
    dados = json.loads(json.dumps(partida.para_dict()))
    copia = Partida.de_dict(dados)
    assert copia.tab == partida.tab
    assert copia.vez == partida.vez
    assert [r.texto for r in copia.historico] == [r.texto for r in partida.historico]


def test_exportar_texto():
    partida = Partida()
    partida.jogar_texto("c3-d4")
    partida.jogar_texto("f6-e5")
    partida.jogar_texto("d4xf6")
    texto = partida.para_texto()
    assert texto.startswith("1. c3-d4 f6-e5\n2. d4xf6")
    assert "a b c d e f g h" in texto


# --- Perft ---------------------------------------------------------------------


def perft(tab, vez, profundidade):
    lances = gerar_lances(tab, vez)
    if profundidade == 1:
        return len(lances)
    return sum(perft(aplicar(tab, lance), -vez, profundidade - 1) for lance in lances)


# Contagem de posicoes a partir da posicao inicial. Trava regressoes no gerador de lances.
@pytest.mark.parametrize(
    ("profundidade", "nos"),
    [(1, 7), (2, 49), (3, 302), (4, 1469), (5, 7473), (6, 37628)],
)
def test_perft(profundidade, nos):
    assert perft(posicao_inicial(), BRANCA, profundidade) == nos
