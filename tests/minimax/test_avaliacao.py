import pytest

from dama.config import obter_config
from dama.minimax.avaliacao import avaliar
from dama.regras.tabuleiro import espelhar, montar, posicao_inicial
from dama.regras.tipos import BRANCA, PRETA

POSICOES = [
    {"c3": "b", "e5": "p"},
    {"a1": "B", "h8": "p", "g7": "p", "c3": "b"},
    {"d4": "b", "e5": "p", "f6": "p", "a7": "P", "h2": "b"},
]


def test_posicao_inicial_e_equilibrada() -> None:
    assert avaliar(posicao_inicial(), BRANCA) == 0
    assert avaliar(posicao_inicial(), PRETA) == 0


@pytest.mark.parametrize("pecas", POSICOES)
def test_troca_de_lado_inverte_o_sinal(pecas: dict[str, str]) -> None:
    tab = montar(pecas)
    assert avaliar(tab, BRANCA) == -avaliar(tab, PRETA)


@pytest.mark.parametrize("pecas", POSICOES)
def test_posicao_espelhada_tem_a_mesma_pontuacao_para_quem_joga(
    pecas: dict[str, str],
) -> None:
    tab = montar(pecas)
    assert avaliar(tab, BRANCA) == avaliar(espelhar(tab), PRETA)


def test_material_domina() -> None:
    uma_a_mais = montar({"a1": "b", "c1": "b", "h8": "p"})
    assert avaliar(uma_a_mais, BRANCA) > obter_config().avaliacao_valor_pedra // 2
    assert avaliar(uma_a_mais, PRETA) < -obter_config().avaliacao_valor_pedra // 2


def test_dama_vale_mais_que_pedra() -> None:
    com_dama = avaliar(montar({"c3": "B", "h8": "p"}), BRANCA)
    com_pedra = avaliar(montar({"c3": "b", "h8": "p"}), BRANCA)
    assert (
        com_dama - com_pedra
        > (obter_config().avaliacao_valor_dama - obter_config().avaliacao_valor_pedra) // 2
    )


def test_pedra_avancada_vale_mais() -> None:
    assert avaliar(montar({"a5": "b", "h8": "p"}), BRANCA) > avaliar(
        montar({"a3": "b", "h8": "p"}), BRANCA
    )
