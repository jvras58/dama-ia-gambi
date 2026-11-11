import pytest

from dama.llm.cliente import CHAT, INDISPONIVEL, OCUPADO, OUTRO, RESPONSES, TEMPO, ErroLLM

MENSAGENS = [{"role": "user", "content": "oi"}]


async def test_lista_participantes(servidor):
    assert await servidor.cliente().participantes() == ["ana-1", "bia-1"]


async def test_sala_inexistente(servidor):
    with pytest.raises(ErroLLM) as info:
        await servidor.cliente(sala="NAOEXISTE").participantes()
    assert info.value.tipo == INDISPONIVEL


async def test_usa_responses_quando_disponivel(servidor):
    servidor.roteiro = ["ola"]
    cliente = servidor.cliente()
    assert await cliente.completar("ana-1", "instrucoes", MENSAGENS) == "ola"
    assert cliente.protocolo == RESPONSES
    assert servidor.pedidos[0]["rota"] == "responses"
    assert servidor.pedidos[0]["model"] == "ana-1"
    assert servidor.pedidos[0]["instructions"] == "instrucoes"


async def test_recua_para_chat_e_lembra(servidor):
    servidor.sem_responses = True
    servidor.roteiro = ["um", "dois"]
    cliente = servidor.cliente()
    assert await cliente.completar("*", "instrucoes", MENSAGENS) == "um"
    assert cliente.protocolo == CHAT
    assert await cliente.completar("*", "instrucoes", MENSAGENS) == "dois"
    assert [p["rota"] for p in servidor.pedidos] == ["chat", "chat"]
    assert servidor.pedidos[0]["messages"][0] == {"role": "system", "content": "instrucoes"}


@pytest.mark.parametrize(
    ("codigo", "tipo"),
    [(409, OCUPADO), (503, INDISPONIVEL), (502, INDISPONIVEL), (500, OUTRO)],
)
async def test_erros_do_hub_sao_classificados(servidor, codigo, tipo):
    servidor.roteiro = [codigo]
    with pytest.raises(ErroLLM) as info:
        await servidor.cliente().completar("ana-1", "i", MENSAGENS)
    assert info.value.tipo == tipo


async def test_tempo_limite(servidor):
    servidor.roteiro = [("lento", 2.0)]
    with pytest.raises(ErroLLM) as info:
        await servidor.cliente(timeout_s=0.1).completar("ana-1", "i", MENSAGENS)
    assert info.value.tipo == TEMPO


async def test_hub_fora_do_ar():
    from dama.llm.cliente import ClienteGambi

    cliente = ClienteGambi("http://127.0.0.1:9", "ABC123", timeout_s=3.0)
    with pytest.raises(ErroLLM) as info:
        await cliente.completar("*", "i", MENSAGENS)
    assert info.value.tipo in (INDISPONIVEL, TEMPO)
