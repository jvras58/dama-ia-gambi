from dama.llm.jogador import (
    ORIGEM_FALLBACK,
    ORIGEM_LLM,
    ORIGEM_UNICO,
    escolher_lance,
)
from dama.minimax.analise import analisar
from dama.regras.partida import Partida
from dama.regras.tabuleiro import montar, notacao


def _posicao():
    partida = Partida()
    return partida, analisar(partida.tab, partida.vez, profundidade=3)


async def _pedir(servidor, partida, analise, **opcoes):
    opcoes.setdefault("espera_ocupado_s", 0.0)
    return await escolher_lance(servidor.cliente(), "ana-1", partida, analise, **opcoes)


async def test_resposta_valida(servidor):
    partida, analise = _posicao()
    servidor.roteiro = ["LANCE: 2\nMOTIVO: ocupa o centro."]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem == ORIGEM_LLM
    assert notacao(decisao.lance) == "c3-d4"
    assert decisao.motivo == "ocupa o centro."
    assert decisao.registro.chamadas == 1
    assert decisao.registro.participante == "ana-1"
    assert decisao.registro.lance == "c3-d4"
    assert decisao.registro.latencia_s > 0
    assert len(servidor.pedidos) == 1


async def test_resposta_invalida_gera_correcao_e_nova_tentativa(servidor):
    partida, analise = _posicao()
    servidor.roteiro = ["Que jogo interessante!", "LANCE: 3\nMOTIVO: agora sim."]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem == ORIGEM_LLM
    assert notacao(decisao.lance) == "c3-b4"
    assert decisao.registro.chamadas == 2
    conversa = servidor.pedidos[1]["input"]
    assert [m["role"] for m in conversa] == ["user", "assistant", "user"]
    assert "Resposta invalida" in conversa[2]["content"]


async def test_ca11_lixo_repetido_vira_fallback_e_nunca_lance_ilegal(servidor):
    partida, analise = _posicao()
    servidor.padrao = "LANCE: 42\nMOTIVO: jogo h9."
    decisao = await _pedir(servidor, partida, analise, tentativas_extras=2)
    assert decisao.origem == ORIGEM_FALLBACK
    assert decisao.lance == analise.melhor.lance
    assert decisao.lance in partida.lances_legais()
    assert decisao.registro.chamadas == 3
    assert len(decisao.registro.respostas) == 3
    assert decisao.registro.seguiu_minimax is True


async def test_ca10_hub_indisponivel_vira_fallback_imediato(servidor):
    partida, analise = _posicao()
    servidor.roteiro = [503]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem == ORIGEM_FALLBACK
    assert decisao.lance == analise.melhor.lance
    assert decisao.registro.chamadas == 1
    assert "503" in decisao.motivo


async def test_participante_ocupado_tenta_de_novo(servidor):
    partida, analise = _posicao()
    servidor.roteiro = [409, "LANCE: 1\nMOTIVO: ok"]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem == ORIGEM_LLM
    assert decisao.registro.chamadas == 2


async def test_tempo_esgotado_vira_fallback(servidor):
    partida, analise = _posicao()
    servidor.roteiro = [("lento", 2.0)]
    decisao = await escolher_lance(servidor.cliente(timeout_s=0.1), "ana-1", partida, analise)
    assert decisao.origem == ORIGEM_FALLBACK


async def test_lance_unico_nao_chama_a_llm(servidor):
    partida = Partida(tab=montar({"c3": "b", "d4": "p", "h8": "p"}))
    analise = analisar(partida.tab, partida.vez, profundidade=2)
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.origem == ORIGEM_UNICO
    assert notacao(decisao.lance) == "c3xe5"
    assert servidor.pedidos == []


async def test_ca15_analise_so_vai_no_prompt_quando_pedida(servidor):
    partida, analise = _posicao()
    await _pedir(servidor, partida, analise, com_analise=False)
    sem = servidor.textos_de(-1)
    await _pedir(servidor, partida, analise, com_analise=True)
    com = servidor.textos_de(-1)
    assert "minimax" not in sem.lower()
    assert "| minimax: " in com and "Minimax" in com


async def test_registro_marca_quando_a_llm_diverge_do_minimax(servidor):
    partida, analise = _posicao()
    pior = analise.lances[-1].lance
    numero = partida.lances_legais().index(pior) + 1
    servidor.roteiro = [f"LANCE: {numero}\nMOTIVO: teimosia."]
    decisao = await _pedir(servidor, partida, analise)
    assert decisao.lance == pior
    assert decisao.registro.seguiu_minimax is (pior == analise.melhor.lance)
