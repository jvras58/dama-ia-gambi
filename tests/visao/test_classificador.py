"""Testes do classificador de cor e da calibracao na posicao inicial."""

import pytest

from apoio.cena import CANTOS_PADRAO, desenhar
from dama.config import obter_config
from dama.regras.gerador import aplicar, gerar_lances
from dama.regras.tabuleiro import N_CASAS, montar, posicao_inicial, tabuleiro_vazio
from dama.regras.tipos import BRANCA, Tabuleiro
from dama.visao.classificador import (
    CalibracaoInvalida,
    ClassificadorCor,
    lado_mais_claro,
    ocupacao_esperada,
    ocupacao_inicial,
)
from dama.visao.localizacao import retificar
from dama.visao.tipos import Imagem, LadoDasBrancas, Ocupacao

POSICOES: list[Tabuleiro] = [
    posicao_inicial(),
    montar({"a1": "b", "c3": "b", "e5": "p", "g7": "p", "h8": "p", "d4": "B", "f6": "P"}),
    montar({"b2": "p", "d2": "b", "f2": "p", "h2": "b", "a7": "b", "c7": "p"}),
    tuple(tabuleiro_vazio()),
]


def _vista(tab: Tabuleiro, lado: LadoDasBrancas = LadoDasBrancas.BAIXO, **opcoes: float) -> Imagem:
    """Vista de topo da foto sintetica de `tab`."""
    brilho = opcoes.get("brilho", 1.0)
    semente = int(opcoes.get("semente", 0))
    reflexo = bool(opcoes.get("reflexo", 0))
    cena = desenhar(tab, lado, brilho=brilho, semente=semente, reflexo=reflexo)
    return retificar(cena, CANTOS_PADRAO)


def _calibrado(lado: LadoDasBrancas = LadoDasBrancas.BAIXO) -> ClassificadorCor:
    """Classificador calibrado com a posicao inicial sintetica."""
    classificador = ClassificadorCor()
    classificador.calibrar(_vista(posicao_inicial(), lado), lado, ocupacao_inicial())
    return classificador


def _acertos(classificador: ClassificadorCor, tab: Tabuleiro, **opcoes: float) -> int:
    """Quantas casas de `tab` sao classificadas certo e com confianca suficiente."""
    minima = obter_config().visao_confianca_min
    leituras = classificador.classificar(_vista(tab, **opcoes), LadoDasBrancas.BAIXO)
    return sum(
        leitura.ocupacao is esperada and leitura.confianca >= minima
        for leitura, esperada in zip(leituras, ocupacao_esperada(tab), strict=True)
    )


def test_ocupacao_esperada_ignora_a_diferenca_entre_pedra_e_dama() -> None:
    """Damas contam como pecas da propria cor: a camera nao as distingue."""
    tab = montar({"a1": "B", "c3": "b", "e5": "P", "g7": "p"})
    assert {ocupacao_esperada(tab)[i] for i in (0, 9)} == {Ocupacao.BRANCA}
    assert ocupacao_esperada(tab).count(Ocupacao.PRETA) == 2
    assert ocupacao_esperada(tab).count(Ocupacao.VAZIA) == N_CASAS - 4


def test_sem_calibracao_nao_classifica() -> None:
    """Classificar antes de calibrar e um erro claro."""
    classificador = ClassificadorCor()
    assert not classificador.calibrado
    with pytest.raises(CalibracaoInvalida):
        classificador.classificar(_vista(posicao_inicial()), LadoDasBrancas.BAIXO)


@pytest.mark.parametrize("lado", list(LadoDasBrancas))
def test_ca01_posicao_inicial_e_lida_por_inteiro(lado: LadoDasBrancas) -> None:
    """CA-01: depois da calibracao, as 24 pecas aparecem nas casas e cores certas."""
    classificador = _calibrado(lado)
    leituras = classificador.classificar(_vista(posicao_inicial(), lado, semente=7), lado)
    assert [x.ocupacao for x in leituras] == ocupacao_inicial()
    assert min(x.confianca for x in leituras) >= obter_config().visao_confianca_min


@pytest.mark.parametrize("lado", list(LadoDasBrancas))
def test_lado_das_brancas_e_descoberto_pela_imagem(lado: LadoDasBrancas) -> None:
    """Na posicao inicial, o lado mais claro da imagem e o das brancas."""
    assert lado_mais_claro(_vista(posicao_inicial(), lado)) is lado


def test_rnf01_acuracia_por_casa_em_posicoes_variadas() -> None:
    """RNF-01: ao menos 99% das casas certas em posicoes e ruidos variados.

    As posicoes incluem uma sequencia de lances a partir da posicao inicial, alem
    de posicoes montadas a mao, cada uma com tres sementes de ruido.
    """
    classificador = _calibrado()
    posicoes = list(POSICOES)
    tab, vez = posicao_inicial(), BRANCA
    for passo in range(20):
        lances = gerar_lances(tab, vez)
        tab, vez = aplicar(tab, lances[passo % len(lances)]), -vez
        posicoes.append(tab)
    certas = total = 0
    for tab in posicoes:
        for semente in (1, 2, 3):
            certas += _acertos(classificador, tab, semente=semente)
            total += N_CASAS
    assert certas / total >= 0.99


@pytest.mark.parametrize("brilho", [0.85, 1.1])
def test_tolera_mudanca_moderada_de_luz(brilho: float) -> None:
    """Uma cena um pouco mais escura ou mais clara que a da calibracao ainda e lida."""
    classificador = _calibrado()
    for tab in POSICOES[:3]:
        assert _acertos(classificador, tab, brilho=brilho) == N_CASAS


def test_reflexo_em_casa_vazia_nao_vira_peca_branca() -> None:
    """Manchas estouradas numa casa vazia sao descartadas e a casa segue vazia."""
    classificador = _calibrado()
    tab = montar({"a1": "b", "h8": "p"})
    assert _acertos(classificador, tab, reflexo=1) == N_CASAS


def test_calibracao_com_tabuleiro_vazio_e_recusada() -> None:
    """Sem as pecas na posicao inicial, a calibracao falha em vez de aprender errado."""
    classificador = ClassificadorCor()
    with pytest.raises(CalibracaoInvalida):
        classificador.calibrar(
            _vista(tuple(tabuleiro_vazio())), LadoDasBrancas.BAIXO, ocupacao_inicial()
        )
    assert not classificador.calibrado


def test_calibracao_exige_as_tres_classes() -> None:
    """Uma posicao sem pecas pretas nao serve para calibrar."""
    classificador = ClassificadorCor()
    tab = montar({"a1": "b"})
    with pytest.raises(CalibracaoInvalida):
        classificador.calibrar(_vista(tab), LadoDasBrancas.BAIXO, ocupacao_esperada(tab))


def test_atualizacao_lenta_acompanha_a_luz() -> None:
    """Atualizar com cenas mais escuras aproxima os centroides da nova iluminacao."""
    classificador = _calibrado()
    assert classificador.centroides is not None
    antes = classificador.centroides.copy()
    escura = _vista(posicao_inicial(), brilho=0.8)
    for _ in range(10):
        classificador.atualizar(escura, LadoDasBrancas.BAIXO, ocupacao_inicial())
    assert (classificador.centroides[:, 0] < antes[:, 0]).all()
    assert _acertos(classificador, posicao_inicial(), brilho=0.8) == N_CASAS
