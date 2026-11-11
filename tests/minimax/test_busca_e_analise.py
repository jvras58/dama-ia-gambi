import time

from dama.minimax.analise import BOM, DUVIDOSO, ERRO, MELHOR, analisar, resumir, rotular
from dama.minimax.busca import LIMIAR_VITORIA, buscar_raiz
from dama.regras.gerador import gerar_lances
from dama.regras.tabuleiro import montar, posicao_inicial
from dama.regras.tipos import BRANCA, PRETA


def test_todos_os_lances_legais_sao_pontuados():
    analise = analisar(posicao_inicial(), BRANCA, profundidade=4)
    assert len(analise.lances) == 7
    assert {a.lance for a in analise.lances} == set(gerar_lances(posicao_inicial(), BRANCA))
    assert analise.profundidade == 4
    pontos = [a.pontuacao for a in analise.lances]
    assert pontos == sorted(pontos, reverse=True)
    assert analise.melhor.rotulo == MELHOR and analise.melhor.perda == 0


def test_busca_e_deterministica():
    tab = montar({"c3": "b", "e3": "b", "g3": "b", "b6": "p", "d6": "p", "f6": "p"})
    a = analisar(tab, BRANCA, profundidade=6)
    b = analisar(tab, BRANCA, profundidade=6)
    assert a == b


def test_posicao_sem_lances():
    analise = analisar(montar({"a1": "b"}), PRETA, profundidade=4)
    assert analise.lances == () and analise.melhor is None


def test_vitoria_em_um_lance():
    # Capturar a ultima peca preta vence na hora.
    analise = analisar(montar({"c3": "b", "d4": "p"}), BRANCA, profundidade=4)
    assert analise.melhor.texto == "c3xe5"
    assert analise.melhor.mate_em == 1
    assert analise.melhor.descricao() == "vence em 1 (melhor)"


def test_vitoria_forcada_em_dois_lances():
    # A pedra preta em a3 so pode descer para b2, onde e capturada.
    tab = montar({"c1": "b", "e1": "b", "a3": "p"})
    analise = analisar(tab, BRANCA, profundidade=6)
    assert analise.melhor.pontuacao >= LIMIAR_VITORIA
    assert analise.melhor.mate_em == 2
    assert analise.melhor.linha  # ha uma continuacao prevista


def test_derrota_forcada_e_sinalizada():
    # As pretas so tem um lance, e ele perde a ultima peca.
    tab = montar({"c1": "b", "a1": "b", "a3": "p"})
    analise = analisar(tab, PRETA, profundidade=6)
    assert len(analise.lances) == 1
    assert analise.melhor.mate_em == -1
    assert analise.melhor.descricao().startswith("perde em 1")


def test_ca13_captura_que_ganha_peca_sem_compensacao_e_o_melhor_lance():
    # Duas capturas de uma peca. c3xa5 fica com a peca; c3xe5 e recapturada por f6xd4.
    # A pedra em g7 protege f6, senao a lei da maioria obrigaria c3xe5xg7.
    tab = montar({"c3": "b", "a1": "b", "b4": "p", "d4": "p", "f6": "p", "g7": "p"})
    analise = analisar(tab, BRANCA, profundidade=4)
    por_texto = {a.texto: a for a in analise.lances}
    assert set(por_texto) == {"c3xa5", "c3xe5"}
    assert analise.melhor.texto == "c3xa5"
    assert analise.melhor.rotulo == MELHOR
    assert por_texto["c3xe5"].perda > 60


def test_ca13_lance_que_entrega_peca_de_graca_e_erro():
    # c3-d4 coloca a pedra na frente de e5, com c3 vazia atras: as pretas capturam de graca.
    # c3-b4 e a1-b2 sao seguros.
    tab = montar({"c3": "b", "a1": "b", "e5": "p", "g7": "p", "h8": "p"})
    analise = analisar(tab, BRANCA, profundidade=4)
    por_texto = {a.texto: a for a in analise.lances}
    assert por_texto["c3-d4"].rotulo == ERRO
    assert por_texto["c3-d4"].perda > 60
    assert analise.melhor.texto != "c3-d4"


def test_quiescencia_nao_para_no_meio_de_uma_troca():
    # Com profundidade 1, a busca ainda ve que c3-d4 perde a pedra para e5xc3.
    tab = montar({"c3": "b", "a1": "b", "e5": "p", "g7": "p", "h8": "p"})
    analise = analisar(tab, BRANCA, profundidade=1)
    por_texto = {a.texto: a for a in analise.lances}
    assert por_texto["c3-d4"].pontuacao < por_texto["c3-b4"].pontuacao - 50


def test_limite_de_tempo_e_respeitado():
    inicio = time.perf_counter()
    resultado = buscar_raiz(posicao_inicial(), BRANCA, profundidade_max=30, tempo_s=0.3)
    decorrido = time.perf_counter() - inicio
    assert decorrido < 1.0
    assert resultado.profundidade >= 1
    assert len(resultado.lances) == 7


def test_rotulos():
    assert rotular(0) == MELHOR
    assert rotular(30) == BOM
    assert rotular(31) == DUVIDOSO
    assert rotular(100) == DUVIDOSO
    assert rotular(101) == ERRO


def test_resumo_do_juiz_por_lado():
    analise = analisar(posicao_inicial(), BRANCA, profundidade=2)
    melhor, pior = analise.lances[0], analise.lances[-1]
    resumo = resumir(
        [
            (BRANCA, melhor.rotulo, melhor.perda),
            (BRANCA, pior.rotulo, pior.perda),
            (PRETA, melhor.rotulo, melhor.perda),
        ]
    )
    assert resumo["brancas"].lances == 2
    assert resumo["brancas"].contagem[MELHOR] >= 1
    assert sum(resumo["brancas"].contagem.values()) == 2
    assert resumo["pretas"].lances == 1
    assert resumo["pretas"].perda_media == 0
    assert resumir([])["brancas"].lances == 0
