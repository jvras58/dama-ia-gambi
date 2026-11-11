"""Testes da leitura da resposta da LLM e da montagem do prompt."""

import pytest

from dama.llm.parser import extrair_lance, extrair_motivo
from dama.llm.prompt import instrucoes, montar_correcao, montar_pedido
from dama.minimax.analise import analisar
from dama.regras.partida import Partida
from dama.regras.tipos import PRETA

LEGAIS = ["a3-b4", "c3-b4", "c3-d4", "e3-d4", "e3-f4", "g3-f4", "g3-h4"]


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("LANCE: 3\nMOTIVO: controla o centro.", 2),
        ("lance: 1", 0),
        ("LANCE 7", 6),
        ("Lance = 2\nMotivo: desenvolve.", 1),
        ("**LANCE:** 4\n**MOTIVO:** bom", 3),
        ("LANCE: #5", 4),
        ("<think>talvez o 2... ou LANCE: 6?</think>\nLANCE: 3\nMOTIVO: ok", 2),
        ("Eu jogaria c3-d4 porque ocupa o centro.", 2),
        ("Minha escolha: C3 - D4.", 2),
        ("g3xh4", 6),
        ("3", 2),
        ("Escolho o 5.", 4),
        ("Opcao 2, pois protege a pedra.", 1),
        ("LANCE: 0", None),
        ("LANCE: 8", None),
        ("LANCE: 99\nMOTIVO: ?", None),
        ("LANCE: 2\nou talvez LANCE: 3", None),
        ("Nao sei jogar damas.", None),
        ("", None),
        ("Fico entre c3-d4 e e3-d4.", None),
        ("b6-a5", None),
        ("Entre 2 e 3, prefiro pensar mais.", None),
        ("A nota e 0.35, entao tanto faz.", None),
    ],
)
def test_extrair_lance(texto: str, esperado: int | None) -> None:
    """Respostas validas viram o indice do lance; as ambiguas ou invalidas, None.

    'g3xh4' vale para o lance simples g3-h4, pois o separador nao importa.
    'b6-a5' e recusado por nao estar na lista de lances legais.
    """
    assert extrair_lance(texto, LEGAIS) == esperado


def test_captura_em_notacao_com_varias_casas() -> None:
    """Uma captura multipla citada em notacao e reconhecida."""
    assert extrair_lance("jogo c3xe5xg7", ["a1-b2", "c3xe5xg7"]) == 1


def test_extrair_motivo() -> None:
    """O motivo e o texto depois de 'MOTIVO:', em uma linha."""
    assert extrair_motivo("LANCE: 3\nMOTIVO: controla o centro.\nextra") == "controla o centro."
    assert extrair_motivo("LANCE: 3") == ""


def test_pedido_sem_analise_lista_todos_os_lances_e_nao_cita_minimax() -> None:
    """Sem analise, o pedido lista todos os lances e nao menciona o Minimax."""
    partida = Partida()
    lances = partida.lances_legais()
    pedido = montar_pedido(partida, lances)
    assert "Voce joga com as brancas" in pedido
    assert "7. g3-f4" in pedido and "1. a3-b4" in pedido
    assert "Escolha um numero de 1 a 7." in pedido
    assert "minimax" not in (pedido + instrucoes(False)).lower()
    assert "nenhum (inicio da partida)" in pedido
    assert "8   p   p   p   p" in pedido


def test_pedido_com_analise_traz_nota_rotulo_e_continuacao() -> None:
    """Com analise, cada lance traz a nota, o rotulo e a continuacao."""
    partida = Partida()
    lances = partida.lances_legais()
    analise = analisar(partida.tab, partida.vez, profundidade=3)
    pedido = montar_pedido(partida, lances, analise)
    linhas = [x for x in pedido.splitlines() if x[:2] in {f"{n}." for n in range(1, 8)}]
    assert len(linhas) == 7
    assert all("| minimax: " in x and "| continuacao: " in x for x in linhas)
    assert "(melhor)" in pedido
    assert "profundidade 3" in pedido
    assert "Minimax" in instrucoes(True)


def test_pedido_para_as_pretas_e_ultimos_lances() -> None:
    """O pedido para as pretas troca os simbolos e cita os ultimos lances."""
    partida = Partida()
    partida.jogar_texto("c3-d4")
    pedido = montar_pedido(partida, partida.lances_legais())
    assert "Voce joga com as pretas: p = pedra, P = dama." in pedido
    assert "descem no diagrama" in pedido
    assert "Ultimos lances: brancas:c3-d4" in pedido
    assert partida.vez == PRETA


def test_correcao_cita_o_intervalo() -> None:
    """A mensagem de correcao diz o intervalo de numeros aceito."""
    assert "de 1 a 7" in montar_correcao(7)
