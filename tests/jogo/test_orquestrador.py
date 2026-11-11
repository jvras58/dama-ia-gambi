"""Testes dos controladores, do orquestrador da partida e da persistencia."""

from pathlib import Path

import pytest

from apoio.servidor_falso import ServidorFalso
from dama.jogo.controladores import (
    Controlador,
    ControladorHumano,
    ControladorLLM,
    ControladorMinimax,
    criar_controlador,
)
from dama.jogo.orquestrador import (
    DadosEvento,
    Estado,
    Evento,
    Modo,
    Orquestrador,
    Ouvinte,
    criar_analisador,
)
from dama.jogo.persistencia import carregar, salvar
from dama.minimax.analise import Rotulo
from dama.regras.partida import LanceIlegal, Partida
from dama.regras.tabuleiro import montar
from dama.regras.tipos import BRANCA, PRETA, Cor

RAPIDO = criar_analisador(profundidade=2, tempo_s=None)


def _orq(
    brancas: Controlador,
    pretas: Controlador,
    *,
    partida: Partida | None = None,
    modo: Modo = Modo.IA_X_IA,
    simulado: bool = True,
    conselheiro: Controlador | None = None,
    cor_assistida: Cor | None = None,
    ouvinte: Ouvinte | None = None,
) -> Orquestrador:
    """Orquestrador com um juiz raso e rapido, para os testes."""
    return Orquestrador(
        partida=partida or Partida(),
        controladores={BRANCA: brancas, PRETA: pretas},
        analisador=RAPIDO,
        modo=modo,
        simulado=simulado,
        conselheiro=conselheiro,
        cor_assistida=cor_assistida,
        ouvinte=ouvinte,
    )


def _escolhe_primeiro(_pedido: str) -> str:
    """Resposta de LLM que sempre escolhe o primeiro lance da lista."""
    return "LANCE: 1\nMOTIVO: o primeiro da lista."


async def test_controlador_minimax_joga_o_melhor_da_analise() -> None:
    """Sem profundidade propria, o Minimax joga o melhor lance da analise do juiz."""
    partida = Partida()
    analise = await RAPIDO(partida)
    decisao = await ControladorMinimax().escolher(partida, analise)
    assert decisao.lance == analise.melhor.lance
    assert decisao.origem == "minimax"


async def test_controlador_minimax_com_profundidade_propria() -> None:
    """Com profundidade propria, o Minimax faz a sua busca e devolve um lance legal."""
    partida = Partida()
    analise = await RAPIDO(partida)
    decisao = await ControladorMinimax(profundidade=1).escolher(partida, analise)
    assert decisao.lance in partida.lances_legais()


async def test_controlador_humano_nao_escolhe() -> None:
    """O controlador humano nunca escolhe um lance."""
    partida = Partida()
    assert await ControladorHumano().escolher(partida, await RAPIDO(partida)) is None


def test_criar_controlador_a_partir_da_descricao(servidor: ServidorFalso) -> None:
    """Cada controlador e recriado da sua descricao; descricoes invalidas sao recusadas."""
    cliente = servidor.cliente()
    for original in (
        ControladorMinimax(3),
        ControladorHumano(),
        ControladorLLM(cliente, "ana-1", com_analise=True),
    ):
        copia = criar_controlador(original.descricao(), cliente)
        assert copia.descricao() == original.descricao()
    with pytest.raises(ValueError):
        criar_controlador({"tipo": "llm", "modelo": "x"})
    with pytest.raises(ValueError):
        criar_controlador({"tipo": "robo"})


async def test_minimax_x_minimax_vai_ate_o_fim_com_rotulos() -> None:
    """Minimax x Minimax termina, com todo lance rotulado e os eventos na ordem.

    O lado que joga com a analise do juiz so recebe o rotulo 'melhor'.
    """
    eventos: list[tuple[Evento, DadosEvento]] = []
    orq = _orq(
        ControladorMinimax(),
        ControladorMinimax(profundidade=1),
        ouvinte=lambda tipo, dados: eventos.append((tipo, dados)),
    )
    assert orq.estado == Estado.PREPARANDO
    await orq.rodar(max_lances=400)
    assert orq.estado == Estado.ENCERRADA
    assert orq.partida.resultado() in ("brancas", "pretas", "empate")
    assert len(orq.lances) == len(orq.partida.historico)
    assert all(isinstance(x.rotulo, Rotulo) for x in orq.lances)
    assert [x.numero for x in orq.lances] == list(range(1, len(orq.lances) + 1))
    assert eventos[0] == ("estado", {"estado": Estado.EM_JOGO, "resultado": None})
    assert eventos[-1][0] == "estado" and eventos[-1][1]["estado"] == Estado.ENCERRADA
    assert sum(1 for tipo, _ in eventos if tipo == "lance") == len(orq.lances)
    assert orq.resumo_do_juiz()["brancas"].contagem["melhor"] == sum(
        1 for x in orq.lances if x.cor == BRANCA
    )


async def test_ca14_llm_x_minimax_ate_o_fim_com_resumo_por_lado(servidor: ServidorFalso) -> None:
    """CA-14: LLM x Minimax termina e o juiz resume cada lado.

    CA-15: no IA x IA, a analise do Minimax nao vai para a LLM.
    """
    servidor.padrao = _escolhe_primeiro
    orq = _orq(ControladorLLM(servidor.cliente(), "ana-1"), ControladorMinimax())
    await orq.rodar(max_lances=400)
    assert orq.estado == Estado.ENCERRADA
    resumo = orq.resumo_do_juiz()
    for lado in ("brancas", "pretas"):
        assert resumo[lado].lances > 0
        assert sum(resumo[lado].contagem.values()) == resumo[lado].lances
    origens = {x.origem for x in orq.lances if x.cor == BRANCA}
    assert "llm" in origens and origens <= {"llm", "unico"}
    assert orq.taxa_de_fallback()["brancas"] == 0.0
    com_registro = [x for x in orq.lances if x.registro_llm]
    assert com_registro and all(x.cor == BRANCA for x in com_registro)
    assert com_registro[0].registro_llm["participante"] == "ana-1"
    assert all("minimax" not in servidor.textos_de(i).lower() for i in range(len(servidor.pedidos)))


async def test_ca07_llm_x_llm_usa_um_participante_por_lado(servidor: ServidorFalso) -> None:
    """CA-07: no LLM x LLM, cada lado consulta o seu participante."""
    servidor.padrao = _escolhe_primeiro
    cliente = servidor.cliente()
    orq = _orq(ControladorLLM(cliente, "ana-1"), ControladorLLM(cliente, "bia-1"))
    await orq.rodar(max_lances=12)
    assert len(orq.lances) == 12
    modelos = [p["model"] for p in servidor.pedidos]
    assert set(modelos) == {"ana-1", "bia-1"}


async def test_ca10_hub_fora_do_ar_a_partida_continua_com_fallback(servidor: ServidorFalso) -> None:
    """CA-10: com o hub fora do ar, a partida segue com os lances do Minimax."""
    servidor.padrao = 503
    orq = _orq(ControladorLLM(servidor.cliente(), "ana-1"), ControladorMinimax())
    await orq.rodar(max_lances=10)
    assert len(orq.lances) == 10
    das_brancas = [x for x in orq.lances if x.cor == BRANCA]
    assert all(x.origem in ("fallback", "unico") for x in das_brancas)
    assert orq.taxa_de_fallback()["brancas"] == 1.0
    assert all(x.rotulo == "melhor" for x in das_brancas)


async def test_pausar_retomar_e_encerrar() -> None:
    """Pausada, a partida nao avanca; retomada, avanca; encerrada, para de vez."""
    orq = _orq(ControladorMinimax(), ControladorMinimax())
    orq.iniciar()
    orq.pausar()
    assert orq.estado == Estado.PAUSADA
    assert await orq.passo() is None
    assert orq.lances == []
    orq.retomar()
    assert orq.estado == Estado.EM_JOGO
    assert await orq.passo() is not None
    orq.encerrar(empate=True)
    assert orq.estado == Estado.ENCERRADA
    assert orq.partida.resultado() == "empate"
    assert await orq.passo() is None


async def test_desfazer_no_orquestrador() -> None:
    """Desfazer remove o ultimo lance e devolve a vez."""
    orq = _orq(ControladorMinimax(), ControladorMinimax())
    await orq.rodar(max_lances=3)
    orq.desfazer()
    assert len(orq.lances) == 2 and len(orq.partida.historico) == 2
    assert orq.partida.vez == BRANCA


async def test_partida_ja_encerrada_ao_iniciar() -> None:
    """Iniciar uma posicao sem lances vai direto para ENCERRADA."""
    orq = _orq(ControladorMinimax(), ControladorMinimax(), partida=Partida(tab=montar({"a1": "b"})))
    orq.partida.vez = PRETA
    orq.iniciar()
    assert orq.estado == Estado.ENCERRADA


async def test_fora_do_modo_simulado_o_lance_da_ia_fica_pendente() -> None:
    """Com tabuleiro fisico, o lance da IA espera a confirmacao da execucao.

    Enquanto aguarda, nenhum outro lance e pedido, e um lance diferente do
    pendente e recusado.
    """
    eventos: list[Evento] = []
    orq = _orq(
        ControladorMinimax(),
        ControladorMinimax(),
        simulado=False,
        ouvinte=lambda tipo, dados: eventos.append(tipo),
    )
    orq.iniciar()
    assert await orq.passo() is None
    assert orq.estado == Estado.AGUARDANDO_EXECUCAO
    assert orq.lances == [] and orq.pendente is not None
    assert "lance_pendente" in eventos
    assert await orq.passo() is None

    outro = next(x for x in orq.partida.lances_legais() if x != orq.pendente.lance)
    with pytest.raises(LanceIlegal):
        await orq.confirmar_execucao(outro)
    assert orq.estado == Estado.AGUARDANDO_EXECUCAO

    jogado = await orq.confirmar_execucao(orq.pendente.lance)
    assert jogado.origem in ("minimax", "unico") and jogado.rotulo == "melhor"
    assert orq.estado == Estado.EM_JOGO and orq.pendente is None


async def test_lance_humano_e_validado_e_julgado() -> None:
    """O lance humano e aplicado e julgado; fora da vez do humano, e recusado.

    Na vez de um humano, `passo` nao faz nada sozinho.
    """
    orq = _orq(ControladorHumano(), ControladorMinimax())
    orq.iniciar()
    assert await orq.passo() is None
    assert orq.estado == Estado.EM_JOGO
    jogado = await orq.lance_humano(orq.partida.lance_de_texto("c3-d4"))
    assert jogado.origem == "humano" and isinstance(jogado.rotulo, Rotulo)
    with pytest.raises(LanceIlegal):
        await orq.lance_humano(orq.partida.lances_legais()[0])


async def test_modo_assistido_sugere_so_na_vez_do_assistido_com_analise(
    servidor: ServidorFalso,
) -> None:
    """No modo assistido, a sugestao so sai na vez do jogador assistido.

    CA-15: aqui a analise do Minimax vai no prompt.
    CA-09: um lance diferente da sugestao e aceito normalmente.
    """
    servidor.padrao = _escolhe_primeiro
    eventos: list[tuple[Evento, DadosEvento]] = []
    orq = _orq(
        ControladorHumano(),
        ControladorHumano(),
        modo=Modo.ASSISTIDO,
        simulado=False,
        conselheiro=ControladorLLM(servidor.cliente(), "ana-1", com_analise=True),
        cor_assistida=BRANCA,
        ouvinte=lambda tipo, dados: eventos.append((tipo, dados)),
    )
    orq.iniciar()
    sugestao = await orq.sugerir()
    assert sugestao is not None and sugestao.origem == "llm"
    assert "| minimax: " in servidor.textos_de(-1)
    tipo, dados = eventos[-1]
    assert tipo == "sugestao" and dados["minimax"]

    outro = next(x for x in orq.partida.lances_legais() if x != sugestao.lance)
    await orq.lance_humano(outro)
    assert orq.partida.vez == PRETA
    assert await orq.sugerir() is None


async def test_salvar_recarregar_e_continuar(tmp_path: Path, servidor: ServidorFalso) -> None:
    """Uma partida salva e recarregada continua de onde parou."""
    servidor.padrao = _escolhe_primeiro
    cliente = servidor.cliente()
    orq = _orq(ControladorLLM(cliente, "ana-1"), ControladorMinimax(profundidade=1))
    await orq.rodar(max_lances=7)
    arquivo = tmp_path / "sub" / "partida.json"
    salvar(orq, arquivo)
    assert not arquivo.with_suffix(".json.tmp").exists()

    salva = carregar(arquivo)
    assert salva.partida.tab == orq.partida.tab
    assert salva.partida.vez == orq.partida.vez
    assert [x.para_dict() for x in salva.lances] == [x.para_dict() for x in orq.lances]
    assert salva.dados["juiz"]["brancas"]["lances"] == 4
    assert salva.dados["lados"]["brancas"] == {
        "tipo": "llm",
        "modelo": "ana-1",
        "com_analise": False,
    }

    continuada = Orquestrador(
        partida=salva.partida,
        controladores={
            cor: criar_controlador(salva.descricao_do_lado(cor), cliente) for cor in (BRANCA, PRETA)
        },
        analisador=RAPIDO,
        lances=salva.lances,
    )
    await continuada.rodar(max_lances=3)
    assert len(continuada.lances) == 10
    assert continuada.lances[-1].numero == 10


def test_arquivo_de_versao_desconhecida_e_recusado(tmp_path: Path) -> None:
    """Um arquivo com outra versao de formato nao e carregado."""
    arquivo = tmp_path / "x.json"
    arquivo.write_text('{"versao": 99}', "utf-8")
    with pytest.raises(ValueError):
        carregar(arquivo)
