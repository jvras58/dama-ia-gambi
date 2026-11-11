from dama.regras.gerador import aplicar, gerar_lances, promove
from dama.regras.tabuleiro import casa, montar, notacao, posicao_inicial
from dama.regras.tipos import BRANCA, DAMA, PEDRA, PRETA, Cor, Lance, Tabuleiro


def lances(pecas: dict[str, str], vez: Cor = BRANCA) -> list[str]:
    return sorted(notacao(lance) for lance in gerar_lances(montar(pecas), vez))


# --- Lances simples ----------------------------------------------------------


def test_posicao_inicial_tem_7_lances_para_cada_lado() -> None:
    assert len(gerar_lances(posicao_inicial(), BRANCA)) == 7
    assert len(gerar_lances(posicao_inicial(), PRETA)) == 7


def test_pedra_so_anda_para_frente() -> None:
    assert lances({"d4": "b"}) == ["d4-c5", "d4-e5"]
    assert lances({"d4": "p"}, PRETA) == ["d4-c3", "d4-e3"]


def test_pedra_na_borda() -> None:
    assert lances({"a3": "b"}) == ["a3-b4"]


def test_pedra_bloqueada_por_peca_propria() -> None:
    assert lances({"d4": "b", "c5": "b", "e5": "b"}) == [
        "c5-b6", "c5-d6", "e5-d6", "e5-f6",
    ]  # fmt: skip


def test_dama_anda_a_distancia_em_tabuleiro_vazio() -> None:
    # d4 enxerga 13 casas: 3+3 numa diagonal, 4+3 na outra.
    assert len(lances({"d4": "B"})) == 13
    assert len(lances({"a1": "B"})) == 7


def test_dama_para_antes_de_peca_propria() -> None:
    assert "a1-c3" not in lances({"a1": "B", "c3": "b"})
    assert "a1-b2" in lances({"a1": "B", "c3": "b"})


# --- Capturas ----------------------------------------------------------------


def test_captura_simples_e_obrigatoria() -> None:
    assert lances({"c3": "b", "d4": "p", "a3": "b"}) == ["c3xe5"]


def test_pedra_captura_para_tras() -> None:
    assert lances({"e5": "b", "d4": "p"}) == ["e5xc3"]


def test_pedra_nao_captura_peca_protegida() -> None:
    assert lances({"c3": "b", "d4": "p", "e5": "p"}) == ["c3-b4"]


def test_captura_multipla_de_pedra() -> None:
    assert lances({"a1": "b", "b2": "p", "d4": "p", "f6": "p"}) == ["a1xc3xe5xg7"]


def test_lei_da_maioria() -> None:
    # c3 pode capturar 1 (via b4) ou 2 (via d4 e f6). So a de 2 e legal.
    pecas = {"c3": "b", "b4": "p", "d4": "p", "f6": "p"}
    assert lances(pecas) == ["c3xe5xg7"]


def test_lei_da_maioria_entre_pecas_diferentes() -> None:
    # a1 captura 3; g3 captura 1. So a de 3 vale.
    pecas = {"a1": "b", "b2": "p", "d4": "p", "f6": "p", "g3": "b", "h4": "p"}
    assert lances(pecas) == ["a1xc3xe5xg7"]


def test_capturas_de_mesmo_tamanho_sao_todas_legais() -> None:
    assert lances({"c3": "b", "b4": "p", "d4": "p"}) == ["c3xa5", "c3xe5"]


def test_dama_captura_a_distancia_e_escolhe_o_pouso() -> None:
    assert lances({"a1": "B", "d4": "p"}) == ["a1xe5", "a1xf6", "a1xg7", "a1xh8"]


def test_dama_nao_salta_duas_pecas_juntas() -> None:
    assert all("x" not in t for t in lances({"a1": "B", "d4": "p", "e5": "p"}))


def test_dama_nao_captura_peca_propria() -> None:
    assert all("x" not in t for t in lances({"a1": "B", "d4": "b"}))


def test_dama_captura_multipla_com_curva() -> None:
    # A dama salta b2 e so do pouso em d4 alcanca e3; depois pousa em f2 ou g1.
    pecas = {"a1": "B", "b2": "p", "e3": "p"}
    assert lances(pecas) == ["a1xd4xf2", "a1xd4xg1"]


def test_peca_capturada_bloqueia_a_passagem_ate_o_fim_do_lance() -> None:
    # A dama captura d4, g5 e g3 e chega a f2. Dali, c5 estaria ao alcance pela diagonal
    # f2-b6 se d4 ja tivesse saido do tabuleiro. Como d4 so sai ao fim do lance, bloqueia.
    pecas = {"a1": "B", "d4": "p", "g5": "p", "g3": "p", "c5": "p"}
    assert lances(pecas) == ["a1xf6xh4xe1", "a1xf6xh4xf2"]


def test_captura_multipla_de_pedra_com_mudanca_de_direcao() -> None:
    pecas = {"c1": "b", "d2": "p", "d4": "p", "b4": "p"}
    assert lances(pecas) == ["c1xe3xc5xa3"]


def test_captura_em_volta_termina_na_casa_de_origem_sem_saltar_peca_duas_vezes() -> None:
    # A origem conta como vazia, entao a pedra pode pousar onde comecou. Ali ela para:
    # as pecas ja saltadas nao podem ser saltadas de novo.
    pecas = {"c3": "b", "d4": "p", "f4": "p", "f2": "p", "d2": "p"}
    assert lances(pecas) == ["c3xe1xg3xe5xc3", "c3xe5xg3xe1xc3"]


# --- Aplicar e promover --------------------------------------------------------


def _unico(pecas: dict[str, str], vez: Cor = BRANCA) -> tuple[Tabuleiro, Lance]:
    tab = montar(pecas)
    (lance,) = gerar_lances(tab, vez)
    return tab, lance


def test_aplicar_lance_simples() -> None:
    tab, lance = _unico({"a3": "b"})
    novo = aplicar(tab, lance)
    assert novo[casa("a3")] == 0
    assert novo[casa("b4")] == PEDRA


def test_aplicar_captura_remove_as_pecas() -> None:
    tab, lance = _unico({"a1": "b", "b2": "p", "d4": "p", "f6": "p"})
    novo = aplicar(tab, lance)
    assert sum(1 for p in novo if p != 0) == 1
    assert novo[casa("g7")] == PEDRA


def test_promocao_ao_terminar_na_ultima_fileira() -> None:
    tab, lance = _unico({"a7": "b"})
    assert promove(tab, lance)
    assert aplicar(tab, lance)[casa("b8")] == DAMA


def test_promocao_das_pretas() -> None:
    tab = montar({"b2": "p"})
    lance = next(x for x in gerar_lances(tab, PRETA) if notacao(x) == "b2-a1")
    assert promove(tab, lance)
    assert aplicar(tab, lance)[casa("a1")] == -DAMA


def test_pedra_que_passa_pela_ultima_fileira_no_meio_da_captura_nao_promove() -> None:
    tab, lance = _unico({"d6": "b", "e7": "p", "g7": "p"})
    assert notacao(lance) == "d6xf8xh6"
    assert not promove(tab, lance)
    assert aplicar(tab, lance)[casa("h6")] == PEDRA


def test_dama_nao_e_promovida_de_novo() -> None:
    tab = montar({"a7": "B"})
    lance = next(x for x in gerar_lances(tab, BRANCA) if notacao(x) == "a7-b8")
    assert not promove(tab, lance)
    assert aplicar(tab, lance)[casa("b8")] == DAMA
