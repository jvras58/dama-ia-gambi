"""Testes da parte web: pagina, saude, WebSocket, papeis e certificado."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from apoio.cena import ALTURA, CANTOS_PADRAO, LARGURA, como_jpeg, desenhar
from dama.config import obter_config
from dama.regras.tabuleiro import N_CASAS, posicao_inicial
from dama.visao.pipeline import Situacao
from dama.web.app import criar_app
from dama.web.protocolo import Papel
from dama.web.servidor import qr_em_texto
from dama.web.sessao import Sessao
from dama.web.tls import (
    ARQUIVO_DA_CHAVE,
    ARQUIVO_DO_CERTIFICADO,
    enderecos_locais,
    garantir_certificado,
)

FRAME = como_jpeg(desenhar(posicao_inicial()))
CANTOS = [[x / LARGURA, y / ALTURA] for x, y in CANTOS_PADRAO]

type Json = dict[str, Any]


@pytest.fixture
def cliente() -> Iterator[TestClient]:
    """Cliente HTTP e WebSocket de uma aplicacao nova, com a thread da visao ligada."""
    with TestClient(criar_app(Sessao())) as cliente:
        yield cliente


def _entrar(ws: WebSocketTestSession, papel: Papel) -> Json:
    """Apresenta-se com o papel pedido e devolve a resposta `bem_vindo`.

    Logo depois dela vem o estado da partida jogada pela tela, que e conferido e
    descartado aqui.
    """
    ws.send_text(json.dumps({"tipo": "ola", "papel": papel}))
    resposta: Json = ws.receive_json()
    assert resposta["tipo"] == "bem_vindo"
    assert ws.receive_json()["tipo"] == "partida"
    return resposta


def _proxima_visao(ws: WebSocketTestSession) -> tuple[Json, bytes | None]:
    """Proxima mensagem `visao` e a previa que vier logo depois dela, se houver.

    Outras mensagens de texto (alertas) que chegarem antes sao puladas.
    """
    while True:
        mensagem: Json = ws.receive_json()
        if mensagem["tipo"] == "visao":
            break
    com_previa = mensagem["situacao"] in (Situacao.SEM_CORES, Situacao.LEITURA)
    return mensagem, ws.receive_bytes() if com_previa else None


def test_pagina_e_arquivos_estaticos(cliente: TestClient) -> None:
    """A pagina do telefone e seus arquivos sao servidos pelo proprio servidor."""
    pagina = cliente.get("/")
    assert pagina.status_code == 200 and "Dama IA Gambi" in pagina.text
    assert 'lang="pt-BR"' in pagina.text
    for arquivo in ("app.js", "estilo.css"):
        assert cliente.get(f"/static/{arquivo}").status_code == 200


def test_saude_sem_camera(cliente: TestClient) -> None:
    """Sem ninguem conectado, a saude mostra que nao ha camera nem frames."""
    saude = cliente.get("/api/saude").json()
    assert saude["ok"] is True and saude["camera_ativa"] is False
    assert saude["fps"] == 0 and saude["situacao"] is None


def test_ola_concede_o_papel_e_informa_a_captura(cliente: TestClient) -> None:
    """A resposta ao `ola` traz o papel e os parametros de captura."""
    with cliente.websocket_connect("/ws") as ws:
        resposta = _entrar(ws, Papel.CAMERA)
        assert resposta["papel"] == Papel.CAMERA
        assert resposta["captura"]["fps"] >= 5
        assert resposta["detector_de_mao"] is False
        assert cliente.get("/api/saude").json()["camera_ativa"] is True


def test_rf_cap_06_segunda_camera_vira_espectadora(cliente: TestClient) -> None:
    """RF-CAP-06: so um aparelho e a camera; o segundo entra como espectador."""
    with cliente.websocket_connect("/ws") as primeira, cliente.websocket_connect("/ws") as outra:
        assert _entrar(primeira, Papel.CAMERA)["papel"] == Papel.CAMERA
        assert _entrar(outra, Papel.CAMERA)["papel"] == Papel.ESPECTADOR
        assert outra.receive_json()["tipo"] == "alerta"


def test_espectador_nao_calibra_nem_envia_frames(cliente: TestClient) -> None:
    """Comandos de calibracao e frames de quem nao e a camera sao recusados."""
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws, Papel.ESPECTADOR)
        ws.send_bytes(FRAME)
        ws.send_text(json.dumps({"tipo": "calibrar_cores"}))
        assert ws.receive_json()["tipo"] == "alerta"
        assert cliente.get("/api/saude").json()["frames_processados"] == 0


def test_mensagem_invalida_vira_alerta(cliente: TestClient) -> None:
    """JSON fora do protocolo nao derruba a conexao: o cliente recebe um alerta."""
    with cliente.websocket_connect("/ws") as ws:
        ws.send_text('{"tipo": "inexistente"}')
        assert ws.receive_json()["tipo"] == "alerta"
        ws.send_text("isto nao e json")
        assert ws.receive_json()["tipo"] == "alerta"
        assert _entrar(ws, Papel.JOGADOR)["papel"] == Papel.JOGADOR


def test_ca01_do_frame_ao_tabuleiro_digital(cliente: TestClient) -> None:
    """CA-01 pela rede: cantos, calibracao e as 24 pecas no tabuleiro digital.

    Percorre os tres passos que o telefone faz: recebe os cantos sugeridos, confirma
    os cantos e calibra as cores com a posicao inicial.
    """
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws, Papel.CAMERA)

        ws.send_bytes(FRAME)
        visao, previa = _proxima_visao(ws)
        assert visao["situacao"] == Situacao.SEM_CANTOS and previa is None
        assert len(visao["cantos_sugeridos"]) == 4

        ws.send_text(json.dumps({"tipo": "cantos", "pontos": CANTOS}))
        ws.send_bytes(FRAME)
        visao, previa = _proxima_visao(ws)
        assert visao["situacao"] == Situacao.SEM_CORES
        assert previa is not None and previa[:2] == b"\xff\xd8"

        ws.send_text(json.dumps({"tipo": "calibrar_cores"}))
        ws.send_bytes(FRAME)
        visao, _ = _proxima_visao(ws)
        assert visao["situacao"] == Situacao.LEITURA
        assert "calibradas" in visao["aviso"]
        ocupacoes = [casa["ocupacao"] for casa in visao["casas"]]
        assert len(ocupacoes) == N_CASAS
        assert ocupacoes.count("branca") == ocupacoes.count("preta") == 12
        assert visao["duvidosas"] == []

    saude = cliente.get("/api/saude").json()
    assert saude["situacao"] == Situacao.LEITURA and saude["frames_processados"] == 3


def test_rf_cap_05_quem_reconecta_recebe_o_estado_atual(cliente: TestClient) -> None:
    """RF-CAP-05: depois de cair, o cliente recebe o ultimo estado ao se apresentar."""
    with cliente.websocket_connect("/ws") as ws:
        _entrar(ws, Papel.CAMERA)
        ws.send_text(json.dumps({"tipo": "cantos", "pontos": CANTOS}))
        ws.send_bytes(FRAME)
        _proxima_visao(ws)
    with cliente.websocket_connect("/ws") as ws:
        assert _entrar(ws, Papel.CAMERA)["papel"] == Papel.CAMERA
        visao, previa = _proxima_visao(ws)
        assert visao["situacao"] == Situacao.SEM_CORES and visao["cantos"] is not None
        assert previa is not None


def test_espectador_acompanha_a_visao(cliente: TestClient) -> None:
    """O que a camera envia chega tambem a quem so esta assistindo."""
    with cliente.websocket_connect("/ws") as camera, cliente.websocket_connect("/ws") as outro:
        _entrar(camera, Papel.CAMERA)
        _entrar(outro, Papel.ESPECTADOR)
        camera.send_bytes(FRAME)
        visao, _ = _proxima_visao(outro)
        assert visao["situacao"] == Situacao.SEM_CANTOS


def test_salvar_frame_grava_o_proximo(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O comando `salvar_frame` grava em disco o proximo frame da camera."""
    monkeypatch.setenv("DAMA_PASTA_FRAMES", str(tmp_path / "frames"))
    obter_config.cache_clear()
    try:
        with cliente.websocket_connect("/ws") as ws:
            _entrar(ws, Papel.CAMERA)
            ws.send_text(json.dumps({"tipo": "salvar_frame"}))
            assert ws.receive_json()["tipo"] == "alerta"
            ws.send_bytes(FRAME)
            _proxima_visao(ws)
        salvos = list((tmp_path / "frames").glob("*.jpg"))
        assert len(salvos) == 1 and salvos[0].read_bytes() == FRAME
    finally:
        monkeypatch.undo()
        obter_config.cache_clear()


def test_certificado_cobre_os_enderecos_e_e_reaproveitado(tmp_path: Path) -> None:
    """O certificado lista os IPs pedidos, e so e refeito quando eles mudam."""
    enderecos = ["192.168.0.10", "127.0.0.1"]
    certificado, chave = garantir_certificado(tmp_path, enderecos)
    assert certificado.name == ARQUIVO_DO_CERTIFICADO and chave.name == ARQUIVO_DA_CHAVE
    lido = x509.load_pem_x509_certificate(certificado.read_bytes())
    nomes = lido.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert {str(ip) for ip in nomes.get_values_for_type(x509.IPAddress)} == set(enderecos)
    assert b"PRIVATE KEY" in chave.read_bytes()

    antes = certificado.read_bytes()
    garantir_certificado(tmp_path, enderecos)
    assert certificado.read_bytes() == antes
    garantir_certificado(tmp_path, [*enderecos, "10.0.0.5"])
    assert certificado.read_bytes() != antes


def test_enderecos_locais_terminam_no_local() -> None:
    """A lista de enderecos sempre inclui 127.0.0.1, por ultimo e sem repeticao."""
    enderecos = enderecos_locais()
    assert enderecos[-1] == "127.0.0.1" and len(set(enderecos)) == len(enderecos)


def test_qr_code_em_texto() -> None:
    """O QR code do endereco sai como varias linhas de caracteres de bloco."""
    desenho = qr_em_texto("https://192.168.0.10:8443")
    assert len(desenho.splitlines()) > 10
