import pytest

from apoio.servidor_falso import ServidorFalso
from dama.llm.cliente import ClienteGambi, ErroLLM, Mensagem, Protocolo, TipoErro

MENSAGENS: list[Mensagem] = [{"role": "user", "content": "oi"}]


async def test_lista_participantes(servidor: ServidorFalso) -> None:
    assert await servidor.cliente().participantes() == ["ana-1", "bia-1"]


async def test_sala_inexistente(servidor: ServidorFalso) -> None:
    with pytest.raises(ErroLLM) as info:
        await servidor.cliente(sala="NAOEXISTE").participantes()
    assert info.value.tipo is TipoErro.INDISPONIVEL


async def test_usa_responses_quando_disponivel(servidor: ServidorFalso) -> None:
    servidor.roteiro = ["ola"]
    cliente = servidor.cliente()
    assert await cliente.completar("ana-1", "instrucoes", MENSAGENS) == "ola"
    assert cliente.protocolo is Protocolo.RESPONSES
    assert servidor.pedidos[0]["rota"] == "responses"
    assert servidor.pedidos[0]["model"] == "ana-1"
    assert servidor.pedidos[0]["instructions"] == "instrucoes"


async def test_recua_para_chat_e_lembra(servidor: ServidorFalso) -> None:
    servidor.sem_responses = True
    servidor.roteiro = ["um", "dois"]
    cliente = servidor.cliente()
    assert await cliente.completar("*", "instrucoes", MENSAGENS) == "um"
    assert cliente.protocolo is Protocolo.CHAT
    assert await cliente.completar("*", "instrucoes", MENSAGENS) == "dois"
    assert [p["rota"] for p in servidor.pedidos] == ["chat", "chat"]
    assert servidor.pedidos[0]["messages"][0] == {"role": "system", "content": "instrucoes"}


@pytest.mark.parametrize(
    ("codigo", "tipo"),
    [
        (409, TipoErro.OCUPADO),
        (503, TipoErro.INDISPONIVEL),
        (502, TipoErro.INDISPONIVEL),
        (500, TipoErro.OUTRO),
    ],
)
async def test_erros_do_hub_sao_classificados(
    servidor: ServidorFalso, codigo: int, tipo: TipoErro
) -> None:
    servidor.roteiro = [codigo]
    with pytest.raises(ErroLLM) as info:
        await servidor.cliente().completar("ana-1", "i", MENSAGENS)
    assert info.value.tipo == tipo


async def test_tempo_limite(servidor: ServidorFalso) -> None:
    servidor.roteiro = [("lento", 2.0)]
    with pytest.raises(ErroLLM) as info:
        await servidor.cliente(timeout_s=0.1).completar("ana-1", "i", MENSAGENS)
    assert info.value.tipo is TipoErro.TEMPO


async def test_hub_fora_do_ar() -> None:
    cliente = ClienteGambi("http://127.0.0.1:9", "ABC123", timeout_s=3.0)
    with pytest.raises(ErroLLM) as info:
        await cliente.completar("*", "i", MENSAGENS)
    assert info.value.tipo in (TipoErro.INDISPONIVEL, TipoErro.TEMPO)
