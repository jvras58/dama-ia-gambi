"""Testes do jogo pela tela: a partida jogada por toque, pelo WebSocket (RF-UI-06)."""

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from apoio.servidor_falso import ServidorFalso
from dama.config import obter_config
from dama.jogo.controladores import (
    ControladorHumano,
    ControladorLLM,
    ControladorMinimax,
    criar_lado,
)
from dama.jogo.orquestrador import criar_analisador
from dama.web.app import criar_app
from dama.web.protocolo import Papel
from dama.web.sessao import Sessao

type Json = dict[str, Any]

LIMITE_DE_MENSAGENS = 200


@pytest.fixture(autouse=True)
def _sem_pausa_e_sem_sala(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tira a pausa entre os lances das IAs e garante que nao ha sala do Gambi."""
    monkeypatch.setenv("DAMA_JOGO_PAUSA_ENTRE_LANCES_S", "0")
    monkeypatch.setenv("DAMA_GAMBI_SALA", "")
    obter_config.cache_clear()
    yield
    monkeypatch.undo()
    obter_config.cache_clear()


@pytest.fixture
def cliente() -> Iterator[TestClient]:
    """Aplicacao nova, com um juiz raso para os testes serem rapidos."""
    with TestClient(criar_app(Sessao(analisador=criar_analisador(2, None)))) as cliente:
        yield cliente


def _mandar(ws: WebSocketTestSession, **mensagem: object) -> None:
    """Envia um comando em JSON."""
    ws.send_text(json.dumps(mensagem))


def _entrar(ws: WebSocketTestSession, papel: Papel = Papel.JOGADOR) -> Json:
    """Apresenta-se e devolve o estado da partida que vem depois do `bem_vindo`."""
    _mandar(ws, tipo="ola", papel=papel)
    assert ws.receive_json()["tipo"] == "bem_vindo"
    estado: Json = ws.receive_json()
    assert estado["tipo"] == "partida"
    return estado


def _ate(ws: WebSocketTestSession, condicao: Callable[[Json], bool]) -> Json:
    """Le mensagens ate chegar um estado da partida que satisfaca `condicao`."""
    for _ in range(LIMITE_DE_MENSAGENS):
        mensagem: Json = ws.receive_json()
        if mensagem["tipo"] == "partida" and condicao(mensagem):
            return mensagem
    raise AssertionError("o estado esperado da partida nao chegou")


def _alerta(ws: WebSocketTestSession) -> str:
    """Le mensagens ate chegar um alerta e devolve o texto dele."""
    for _ in range(LIMITE_DE_MENSAGENS):
        mensagem: Json = ws.receive_json()
        if mensagem["tipo"] == "alerta":
            return str(mensagem["mensagem"])
    raise AssertionError("o alerta esperado nao chegou")


def _vez_do_humano(com_lances: int) -> Callable[[Json], bool]:
    """Condicao: e a vez do humano e ja foram jogados `com_lances` lances."""
    return lambda e: bool(e["humano_na_vez"]) and len(e["lances"]) == com_lances


def test_criar_lado_entende_os_textos_da_interface(servidor: ServidorFalso) -> None:
    """Cada texto de lado vira o controlador certo; os invalidos sao recusados."""
    assert isinstance(criar_lado("humano"), ControladorHumano)
    assert isinstance(criar_lado(" minimax "), ControladorMinimax)
    raso = criar_lado("minimax:2")
    assert isinstance(raso, ControladorMinimax) and raso.profundidade == 2
    llm = criar_lado("llm:ana-1", servidor.cliente())
    assert isinstance(llm, ControladorLLM) and llm.modelo == "ana-1"
    padrao = criar_lado("llm", servidor.cliente())
    assert isinstance(padrao, ControladorLLM) and padrao.modelo == "*"
    for invalido in ("", "robo", "minimax:x", "humano:1", "llm:ana-1"):
        with pytest.raises(ValueError):
            criar_lado(invalido)


def test_antes_da_primeira_partida_o_estado_vem_vazio(cliente: TestClient) -> None:
    """Quem entra sem partida criada recebe um estado inativo e sem Gambi."""
    with cliente.websocket_connect("/ws") as ws:
        estado = _entrar(ws)
        assert estado["ativa"] is False and estado["legais"] == []
        assert estado["gambi"] is False
        config = obter_config()
        assert estado["lados"] == {"brancas": config.jogo_brancas, "pretas": config.jogo_pretas}
        assert [x["valor"] for x in estado["opcoes"]] == [
            "humano",
            f"minimax:{config.jogo_profundidade_facil}",
            f"minimax:{config.jogo_profundidade_media}",
            "minimax",
            "llm",
        ]
        _mandar(ws, tipo="jogar", lance="c3-d4")
        assert "nenhuma partida" in _alerta(ws)


def test_humano_joga_e_o_minimax_responde(cliente: TestClient) -> None:
    """RF-UI-06: o humano joga por notacao, o Minimax responde e o juiz rotula."""
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws)
        _mandar(ws, tipo="nova_partida", brancas="humano", pretas="minimax:1")
        inicio = _ate(ws, _vez_do_humano(0))
        assert inicio["ativa"] and inicio["vez"] == "brancas"
        assert sorted(inicio["casas"]) == [-1] * 12 + [0] * 8 + [1] * 12
        assert len(inicio["legais"]) == 7
        legal = next(x for x in inicio["legais"] if x["texto"] == "c3-d4")
        assert len(legal["casas"]) == 2 and legal["capturas"] == []

        _mandar(ws, tipo="jogar", lance="c3-d4")
        depois = _ate(ws, _vez_do_humano(2))
        meu, dela = depois["lances"]
        assert (meu["lance"], meu["cor"], meu["origem"]) == ("c3-d4", "brancas", "humano")
        assert meu["rotulo"] is not None
        assert dela["cor"] == "pretas" and dela["origem"] in ("minimax", "unico")
        assert len(depois["ultimo"]) >= 2 and depois["pensando"] is False


def test_lance_ilegal_vira_alerta_e_nao_muda_a_partida(cliente: TestClient) -> None:
    """Um lance fora da lista de legais e recusado pelo motor de regras."""
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws)
        _mandar(ws, tipo="nova_partida", brancas="humano", pretas="humano")
        _ate(ws, _vez_do_humano(0))
        _mandar(ws, tipo="jogar", lance="c3-c4")
        assert "ilegal" in _alerta(ws)
        _mandar(ws, tipo="jogar", lance="a3-b4")
        assert _ate(ws, _vez_do_humano(1))["vez"] == "pretas"


def test_espectador_nao_joga(cliente: TestClient) -> None:
    """Comandos do jogo vindos de um espectador sao recusados."""
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws, Papel.ESPECTADOR)
        _mandar(ws, tipo="nova_partida", brancas="humano", pretas="humano")
        assert "Espectadores" in _alerta(ws)
        assert cliente.app.state.sessao.mesa.orquestrador is None  # type: ignore[attr-defined]


def test_todos_os_clientes_veem_a_mesma_partida(cliente: TestClient) -> None:
    """O estado da partida e difundido, e quem entra depois recebe a posicao atual."""
    with cliente.websocket_connect("/ws") as jogador:
        _entrar(jogador)
        _mandar(jogador, tipo="nova_partida", brancas="humano", pretas="humano")
        _ate(jogador, _vez_do_humano(0))
        _mandar(jogador, tipo="jogar", lance="e3-f4")
        _ate(jogador, _vez_do_humano(1))
        with cliente.websocket_connect("/ws") as outro:
            estado = _entrar(outro, Papel.ESPECTADOR)
            assert [x["lance"] for x in estado["lances"]] == ["e3-f4"]


def test_desfazer_volta_a_vez_do_humano(cliente: TestClient) -> None:
    """Contra uma IA, desfazer tira a resposta dela e o lance do humano."""
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws)
        _mandar(ws, tipo="desfazer")
        assert "nenhuma partida" in _alerta(ws)
        _mandar(ws, tipo="nova_partida", brancas="humano", pretas="minimax:1")
        _ate(ws, _vez_do_humano(0))
        _mandar(ws, tipo="desfazer")
        assert "desfazer" in _alerta(ws)
        _mandar(ws, tipo="jogar", lance="c3-d4")
        _ate(ws, _vez_do_humano(2))
        _mandar(ws, tipo="desfazer")
        voltou = _ate(ws, _vez_do_humano(0))
        assert voltou["vez"] == "brancas" and voltou["ultimo"] == []


def test_dica_do_minimax_quando_nao_ha_gambi(cliente: TestClient) -> None:
    """Sem sala do Gambi, a dica vem do Minimax e aponta um lance legal."""
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws)
        _mandar(ws, tipo="nova_partida", brancas="humano", pretas="minimax:1")
        inicio = _ate(ws, _vez_do_humano(0))
        _mandar(ws, tipo="dica")
        dica = _ate(ws, lambda e: e["dica"] is not None)["dica"]
        assert dica["lance"] in [x["texto"] for x in inicio["legais"]]
        assert dica["origem"] == "minimax" and dica["minimax"]
        _mandar(ws, tipo="jogar", lance=dica["lance"])
        assert _ate(ws, _vez_do_humano(2))["dica"] is None


def test_ia_contra_ia_joga_sozinha(cliente: TestClient) -> None:
    """Com dois lados de IA, os lances saem sem ninguem tocar na tela."""
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws)
        _mandar(ws, tipo="nova_partida", brancas="minimax:1", pretas="minimax:1")
        estado = _ate(ws, lambda e: len(e["lances"]) >= 4)
        assert estado["humano_na_vez"] is False and estado["legais"] == []
        _mandar(ws, tipo="desfazer")
        assert "humano" in _alerta(ws)


def test_lado_llm_sem_sala_e_recusado(cliente: TestClient) -> None:
    """Sem sala do Gambi configurada, pedir um lado LLM vira alerta."""
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws)
        _mandar(ws, tipo="nova_partida", brancas="llm", pretas="humano")
        assert "Gambi" in _alerta(ws)
        _mandar(ws, tipo="nova_partida", brancas="robo", pretas="humano")
        assert "invalido" in _alerta(ws)


def test_llm_do_gambi_joga_e_da_dica(servidor: ServidorFalso) -> None:
    """Com o Gambi, a LLM joga um lado e tambem e a conselheira do humano."""
    sessao = Sessao(analisador=criar_analisador(2, None), cliente=servidor.cliente())
    with TestClient(criar_app(sessao)) as cliente, cliente.websocket_connect("/ws") as ws:
        assert _entrar(ws)["gambi"] is True
        _mandar(ws, tipo="nova_partida", brancas="llm:ana-1", pretas="humano")
        estado = _ate(ws, _vez_do_humano(1))
        assert estado["lances"][0]["origem"] == "llm" and estado["vez"] == "pretas"
        assert estado["lances"][0]["motivo"]
        _mandar(ws, tipo="dica")
        dica = _ate(ws, lambda e: e["dica"] is not None)["dica"]
        assert dica["origem"] == "llm"
        assert "Analise" in servidor.textos_de() or "analise" in servidor.textos_de()
