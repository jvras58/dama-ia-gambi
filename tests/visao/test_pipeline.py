"""Testes do pipeline de visao: do frame JPEG a leitura das casas."""

import threading
from pathlib import Path

import numpy as np
import pytest

from apoio.cena import ALTURA, CANTOS_PADRAO, LARGURA, como_jpeg, desenhar
from dama.regras.tabuleiro import montar, posicao_inicial
from dama.regras.tipos import Tabuleiro
from dama.visao.classificador import ocupacao_esperada, ocupacao_inicial
from dama.visao.localizacao import girar
from dama.visao.pipeline import (
    ResultadoVisao,
    Situacao,
    TrabalhadorDeVisao,
    Visao,
    cantos_de,
    salvar_frame,
)
from dama.visao.tipos import Cantos, Imagem, LadoDasBrancas

TOLERANCIA = 0.01
FIXTURES = Path(__file__).parent.parent / "fixtures" / "tabuleiro"
LARGURA_DA_FOTO = 720
ALTURA_DA_FOTO = 1280
CANTOS_DAS_FOTOS: dict[str, Cantos] = {
    "inicial_espelhada_em_fundo_vermelho.jpg": ((72, 230), (677, 258), (667, 877), (31, 850)),
    "inicial_espelhada_em_fundo_rosa.jpg": ((80, 106), (680, 120), (670, 712), (48, 688)),
}


def _normalizados(cantos: Cantos = CANTOS_PADRAO) -> Cantos:
    """Cantos da cena sintetica como fracoes da largura e da altura."""
    p = [(x / LARGURA, y / ALTURA) for x, y in cantos]
    return (p[0], p[1], p[2], p[3])


def _frame(tab: Tabuleiro, lado: LadoDasBrancas = LadoDasBrancas.BAIXO, semente: int = 0) -> bytes:
    """Frame JPEG da cena sintetica de `tab`."""
    return como_jpeg(desenhar(tab, lado, semente=semente))


def _calibrada(lado: LadoDasBrancas = LadoDasBrancas.BAIXO) -> Visao:
    """Visao com cantos confirmados e cores calibradas na posicao inicial."""
    visao = Visao()
    visao.definir_cantos(_normalizados())
    visao.pedir_calibracao()
    resultado = visao.processar(_frame(posicao_inicial(), lado))
    assert resultado.situacao is Situacao.LEITURA, resultado.aviso
    return visao


class _MaoFalsa:
    """Sensor de mao de mentira, que responde o que o teste mandar."""

    def __init__(self) -> None:
        """Comeca sem mao sobre o tabuleiro."""
        self.presente = False

    def ha_mao_sobre(self, imagem: Imagem, cantos: Cantos, instante_s: float) -> bool:
        """Devolve o valor configurado pelo teste."""
        return self.presente


def test_bytes_que_nao_sao_imagem() -> None:
    """Lixo no lugar do JPEG vira FRAME_INVALIDO, sem excecao."""
    assert Visao().processar(b"nao e um jpeg").situacao is Situacao.FRAME_INVALIDO
    assert Visao().processar(b"").situacao is Situacao.FRAME_INVALIDO


def test_sem_cantos_a_visao_sugere_os_automaticos() -> None:
    """Antes da confirmacao, o resultado traz os cantos achados sozinhos."""
    resultado = Visao().processar(_frame(posicao_inicial()))
    assert resultado.situacao is Situacao.SEM_CANTOS
    assert (resultado.largura, resultado.altura) == (LARGURA, ALTURA)
    assert resultado.cantos is None and resultado.cantos_sugeridos is not None
    desvios = np.abs(np.array(resultado.cantos_sugeridos) - np.array(_normalizados()))
    assert float(desvios.max()) < TOLERANCIA


def test_mesa_sem_tabuleiro_nao_sugere_cantos() -> None:
    """Sem tabuleiro na imagem, nao ha sugestao de cantos."""
    mesa = np.full((ALTURA, LARGURA, 3), 205, dtype=np.uint8)
    resultado = Visao().processar(como_jpeg(mesa))
    assert resultado.situacao is Situacao.SEM_CANTOS and resultado.cantos_sugeridos is None


def test_com_cantos_e_sem_cores_vem_a_previa() -> None:
    """Com os cantos confirmados, a visao manda a previa e espera a calibracao."""
    visao = Visao()
    visao.definir_cantos(_normalizados())
    resultado = visao.processar(_frame(posicao_inicial()))
    assert resultado.situacao is Situacao.SEM_CORES
    assert resultado.previa is not None and resultado.previa[:2] == b"\xff\xd8"
    assert resultado.leituras == ()


def test_cantos_girados_sao_reorientados() -> None:
    """Cantos confirmados com um quarto de volta sao corrigidos no frame seguinte."""
    visao = Visao()
    visao.definir_cantos(_normalizados(girar(CANTOS_PADRAO)))
    visao.pedir_calibracao()
    resultado = visao.processar(_frame(posicao_inicial()))
    assert resultado.situacao is Situacao.LEITURA, resultado.aviso


def test_ca01_calibracao_e_leitura_da_posicao_inicial() -> None:
    """CA-01: depois de calibrar, as 24 pecas sao lidas nas casas e cores certas."""
    for lado in LadoDasBrancas:
        visao = _calibrada(lado)
        resultado = visao.processar(_frame(posicao_inicial(), lado, semente=3))
        assert resultado.situacao is Situacao.LEITURA
        assert resultado.lado_das_brancas is lado
        assert [x.ocupacao for x in resultado.leituras] == ocupacao_inicial()
        assert resultado.duvidosas == ()
        assert resultado.duracao_ms > 0


def test_mover_uma_peca_muda_a_leitura() -> None:
    """Depois de um lance no tabuleiro, a leitura mostra a nova posicao."""
    visao = _calibrada()
    depois = montar({"c3": "b", "d4": "b", "f6": "p"})
    resultado = visao.processar(_frame(depois, semente=5))
    assert [x.ocupacao for x in resultado.leituras] == ocupacao_esperada(depois)


def test_calibracao_recusada_avisa_e_nao_calibra() -> None:
    """Pedir calibracao com o tabuleiro vazio devolve um aviso e segue sem cores."""
    visao = Visao()
    visao.definir_cantos(_normalizados())
    visao.pedir_calibracao()
    resultado = visao.processar(_frame(montar({"a1": "b"})))
    assert resultado.situacao is Situacao.SEM_CORES
    assert "recusada" in resultado.aviso
    assert visao.processar(_frame(posicao_inicial())).aviso == ""


@pytest.mark.parametrize("lado", list(LadoDasBrancas))
def test_tabuleiro_com_casa_clara_a_esquerda_e_lido_espelhado(lado: LadoDasBrancas) -> None:
    """Com a casa clara no canto inferior esquerdo dos jogadores, a leitura e espelhada.

    A cena transposta e o espelho de uma montagem correta: as pecas ficam em cima e
    embaixo, mas a casa do canto inferior esquerdo de quem joga e clara. A calibracao
    aceita, avisa do espelho e le a posicao inicial; recalibrar mantem o espelho.
    """
    cena = como_jpeg(np.ascontiguousarray(desenhar(posicao_inicial(), lado).transpose(1, 0, 2)))
    p = [(y / ALTURA, x / LARGURA) for x, y in CANTOS_PADRAO]
    visao = Visao()
    visao.definir_cantos((p[0], p[3], p[2], p[1]))
    assert not visao.processar(cena).espelhado
    for _ in range(2):
        visao.pedir_calibracao()
        resultado = visao.processar(cena)
        assert resultado.situacao is Situacao.LEITURA, resultado.aviso
        assert resultado.espelhado
        assert [x.ocupacao for x in resultado.leituras] == ocupacao_inicial()
        assert resultado.duvidosas == ()
    visao.limpar_cantos()
    assert not visao.processar(cena).espelhado


def test_montagem_normal_nao_e_espelhada() -> None:
    """Com a casa escura no canto inferior esquerdo, a leitura nao e espelhada."""
    resultado = _calibrada().processar(_frame(posicao_inicial()))
    assert not resultado.espelhado


@pytest.mark.parametrize("nome", list(CANTOS_DAS_FOTOS))
def test_fotos_reais_da_posicao_inicial_sao_lidas(nome: str) -> None:
    """Nas fotos reais com as 24 pecas, cantos conferidos a olho bastam para calibrar.

    O tabuleiro esta com a casa clara a esquerda dos jogadores nas duas fotos, e os
    cantos sao os da area de jogo, marcados a mao sobre a foto.
    """
    p = [(x / LARGURA_DA_FOTO, y / ALTURA_DA_FOTO) for x, y in CANTOS_DAS_FOTOS[nome]]
    dados = (FIXTURES / nome).read_bytes()
    visao = Visao()
    visao.definir_cantos((p[0], p[1], p[2], p[3]))
    visao.pedir_calibracao()
    resultado = visao.processar(dados)
    assert resultado.situacao is Situacao.LEITURA, resultado.aviso
    assert resultado.espelhado
    assert [x.ocupacao for x in resultado.leituras] == ocupacao_inicial()
    assert resultado.duvidosas == ()


def test_inverter_lados_gira_a_leitura() -> None:
    """Trocar o lado das brancas le o mesmo frame girado em 180 graus."""
    visao = _calibrada()
    visao.inverter_lados()
    resultado = visao.processar(_frame(posicao_inicial()))
    assert resultado.lado_das_brancas is LadoDasBrancas.CIMA
    assert [x.ocupacao for x in resultado.leituras] == ocupacao_inicial()[::-1]


def test_limpar_cantos_volta_a_sugerir() -> None:
    """Depois de limpar os cantos, a visao volta ao passo de localizacao."""
    visao = _calibrada()
    visao.limpar_cantos()
    assert visao.processar(_frame(posicao_inicial())).situacao is Situacao.SEM_CANTOS


def test_rf_vis_06_mao_sobre_o_tabuleiro_suspende_a_leitura() -> None:
    """RF-VIS-06: com mao sobre o tabuleiro, nao ha leitura; sem mao, ela volta."""
    sensor = _MaoFalsa()
    visao = _calibrada()
    visao.sensor_de_mao = sensor
    sensor.presente = True
    resultado = visao.processar(_frame(posicao_inicial()))
    assert resultado.situacao is Situacao.MAO and resultado.leituras == ()
    sensor.presente = False
    assert visao.processar(_frame(posicao_inicial())).situacao is Situacao.LEITURA


def test_rnf03_processa_ao_menos_cinco_frames_por_segundo() -> None:
    """RNF-03: um frame de 1280 px e processado em menos de 200 ms."""
    visao = _calibrada()
    frame = _frame(posicao_inicial())
    duracoes = sorted(visao.processar(frame).duracao_ms for _ in range(5))
    assert duracoes[len(duracoes) // 2] < 200


def test_cantos_de_exige_quatro_pontos() -> None:
    """Uma lista com numero errado de pontos nao vira `Cantos`."""
    assert cantos_de([(0, 0), (1, 0), (1, 1), (0, 1)]) == ((0, 0), (1, 0), (1, 1), (0, 1))
    with pytest.raises(ValueError):
        cantos_de([(0, 0)])


def test_salvar_frame_grava_o_jpeg(tmp_path: Path) -> None:
    """O frame salvo em disco tem exatamente os bytes recebidos."""
    dados = _frame(posicao_inicial())
    caminho = salvar_frame(dados, tmp_path / "sub")
    assert caminho.read_bytes() == dados and caminho.suffix == ".jpg"


def test_trabalhador_entrega_resultados_e_descarta_frames_atrasados() -> None:
    """O trabalhador processa em outra thread e nunca acumula mais de um frame."""
    recebidos: list[ResultadoVisao] = []
    chegou = threading.Event()

    def ao_resultado(resultado: ResultadoVisao) -> None:
        """Guarda o resultado e avisa o teste."""
        recebidos.append(resultado)
        chegou.set()

    trabalhador = TrabalhadorDeVisao(Visao(), ao_resultado)
    frame = _frame(posicao_inicial())
    for _ in range(6):
        trabalhador.enviar(frame)
    assert trabalhador.descartados == 5
    trabalhador.iniciar()
    assert chegou.wait(timeout=10)
    trabalhador.parar()
    assert len(recebidos) == 1 and recebidos[0].situacao is Situacao.SEM_CANTOS
    assert trabalhador.processados == 1
