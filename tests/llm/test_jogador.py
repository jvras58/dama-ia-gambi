from apoio.servidor_falso import ServidorFalso
from dama.llm.jogador import Decisao, Origem, RegistroLLM, escolher_lance
from dama.minimax.analise import AnaliseLance, AnalisePosicao, analisar
from dama.regras.partida import Partida
from dama.regras.tabuleiro import montar, notacao


def _posicao() -> tuple[Partida, AnalisePosicao]:
    partida = Partida()
    return partida, analisar(partida.tab, partida.vez, profundidade=3)


async def _pedir(
    servidor: ServidorFalso,
    partida: Partida,
    analise: AnalisePosicao,
    com_analise: bool = False,
    tentativas_extras: int | None = None,
) -> Decisao:
    return await escolher_lance(
        servidor.cliente(),
        "ana-1",
        partida,
        analise,
        com_analise=com_analise,
        tentativas_extras=tentativas_extras,
        espera_ocupado_s=0.0,
    )


def _registro(decisao: Decisao) -> RegistroLLM:
    assert decisao.registro is not None
    return decisao.registro


def _melhor(analise: AnalisePosicao) -> AnaliseLance:
    assert analise.melhor is not None
    return analise.melhor


async def test_resposta_valida(servidor: ServidorFalso) -> None:
    partida, analise = _posicao()
    servidor.roteiro = ["LANCE: 2\nMOTIVO: ocupa o centro."]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem is Origem.LLM
    assert notacao(decisao.lance) == "c3-d4"
    assert decisao.motivo == "ocupa o centro."
    assert _registro(decisao).chamadas == 1
    assert _registro(decisao).participante == "ana-1"
    assert _registro(decisao).lance == "c3-d4"
    assert _registro(decisao).latencia_s > 0
    assert len(servidor.pedidos) == 1


async def test_resposta_invalida_gera_correcao_e_nova_tentativa(servidor: ServidorFalso) -> None:
    partida, analise = _posicao()
    servidor.roteiro = ["Que jogo interessante!", "LANCE: 3\nMOTIVO: agora sim."]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem is Origem.LLM
    assert notacao(decisao.lance) == "c3-b4"
    assert _registro(decisao).chamadas == 2
    conversa = servidor.pedidos[1]["input"]
    assert [m["role"] for m in conversa] == ["user", "assistant", "user"]
    assert "Resposta invalida" in conversa[2]["content"]


async def test_ca11_lixo_repetido_vira_fallback_e_nunca_lance_ilegal(
    servidor: ServidorFalso,
) -> None:
    partida, analise = _posicao()
    servidor.padrao = "LANCE: 42\nMOTIVO: jogo h9."
    decisao = await _pedir(servidor, partida, analise, tentativas_extras=2)
    assert decisao.origem is Origem.FALLBACK
    assert decisao.lance == _melhor(analise).lance
    assert decisao.lance in partida.lances_legais()
    assert _registro(decisao).chamadas == 3
    assert len(_registro(decisao).respostas) == 3
    assert _registro(decisao).seguiu_minimax is True


async def test_ca10_hub_indisponivel_vira_fallback_imediato(servidor: ServidorFalso) -> None:
    partida, analise = _posicao()
    servidor.roteiro = [503]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem is Origem.FALLBACK
    assert decisao.lance == _melhor(analise).lance
    assert _registro(decisao).chamadas == 1
    assert "503" in decisao.motivo


async def test_participante_ocupado_tenta_de_novo(servidor: ServidorFalso) -> None:
    partida, analise = _posicao()
    servidor.roteiro = [409, "LANCE: 1\nMOTIVO: ok"]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem is Origem.LLM
    assert _registro(decisao).chamadas == 2


async def test_tempo_esgotado_vira_fallback(servidor: ServidorFalso) -> None:
    partida, analise = _posicao()
    servidor.roteiro = [("lento", 2.0)]
    decisao = await escolher_lance(servidor.cliente(timeout_s=0.1), "ana-1", partida, analise)
    assert decisao.origem is Origem.FALLBACK


async def test_lance_unico_nao_chama_a_llm(servidor: ServidorFalso) -> None:
    partida = Partida(tab=montar({"c3": "b", "d4": "p", "h8": "p"}))
    analise = analisar(partida.tab, partida.vez, profundidade=2)
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem is Origem.UNICO
    assert notacao(decisao.lance) == "c3xe5"
    assert servidor.pedidos == []


async def test_ca15_analise_so_vai_no_prompt_quando_pedida(servidor: ServidorFalso) -> None:
    partida, analise = _posicao()
    await _pedir(servidor, partida, analise, com_analise=False)
    sem = servidor.textos_de(-1)
    await _pedir(servidor, partida, analise, com_analise=True)
    com = servidor.textos_de(-1)
    assert "minimax" not in sem.lower()
    assert "| minimax: " in com and "Minimax" in com


async def test_registro_marca_quando_a_llm_diverge_do_minimax(servidor: ServidorFalso) -> None:
    partida, analise = _posicao()
    pior = analise.lances[-1].lance
    numero = partida.lances_legais().index(pior) + 1
    servidor.roteiro = [f"LANCE: {numero}\nMOTIVO: teimosia."]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.lance == pior
    assert _registro(decisao).seguiu_minimax is (pior == _melhor(analise).lance)
