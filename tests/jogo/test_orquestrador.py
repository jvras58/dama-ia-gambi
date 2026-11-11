import pytest

from dama.jogo.controladores import (
    ControladorHumano,
    ControladorLLM,
    ControladorMinimax,
    criar_controlador,
)
from dama.jogo.orquestrador import (
    AGUARDANDO_EXECUCAO,
    EM_JOGO,
    ENCERRADA,
    PAUSADA,
    PREPARANDO,
    Orquestrador,
    criar_analisador,
)
from dama.jogo.persistencia import carregar, salvar
from dama.minimax.analise import ROTULOS
from dama.regras.partida import LanceIlegal, Partida
from dama.regras.tabuleiro import montar
from dama.regras.tipos import BRANCA, PRETA

RAPIDO = criar_analisador(profundidade=2, tempo_s=None)


def _orq(brancas, pretas, **opcoes) -> Orquestrador:
    opcoes.setdefault("partida", Partida())
    opcoes.setdefault("analisador", RAPIDO)
    return Orquestrador(controladores={BRANCA: brancas, PRETA: pretas}, **opcoes)


def _escolhe_primeiro(_pedido: str) -> str:
    return "LANCE: 1\nMOTIVO: o primeiro da lista."


# --- Controladores -------------------------------------------------------------


async def test_controlador_minimax_joga_o_melhor_da_analise():
    partida = Partida()
    analise = await RAPIDO(partida)
    decisao = await ControladorMinimax().escolher(partida, analise)
    assert decisao.lance == analise.melhor.lance
    assert decisao.origem == "minimax"


async def test_controlador_minimax_com_profundidade_propria():
    partida = Partida()
    analise = await RAPIDO(partida)
    decisao = await ControladorMinimax(profundidade=1).escolher(partida, analise)
    assert decisao.lance in partida.lances_legais()


async def test_controlador_humano_nao_escolhe():
    partida = Partida()
    assert await ControladorHumano().escolher(partida, await RAPIDO(partida)) is None


def test_criar_controlador_a_partir_da_descricao(servidor):
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


# --- Partidas simuladas --------------------------------------------------------


async def test_minimax_x_minimax_vai_ate_o_fim_com_rotulos():
    eventos = []
    orq = _orq(
        ControladorMinimax(),
        ControladorMinimax(profundidade=1),
        ouvinte=lambda tipo, dados: eventos.append((tipo, dados)),
    )
    assert orq.estado == PREPARANDO
    await orq.rodar(max_lances=400)
    assert orq.estado == ENCERRADA
    assert orq.partida.resultado() in ("brancas", "pretas", "empate")
    assert len(orq.lances) == len(orq.partida.historico)
    assert all(x.rotulo in ROTULOS for x in orq.lances)
    assert [x.numero for x in orq.lances] == list(range(1, len(orq.lances) + 1))
    assert eventos[0] == ("estado", {"estado": EM_JOGO, "resultado": None})
    assert eventos[-1][0] == "estado" and eventos[-1][1]["estado"] == ENCERRADA
    assert sum(1 for tipo, _ in eventos if tipo == "lance") == len(orq.lances)
    # O lado que joga com a analise do juiz so recebe "melhor".
    assert orq.resumo_do_juiz()["brancas"].contagem["melhor"] == sum(
        1 for x in orq.lances if x.cor == BRANCA
    )


async def test_ca14_llm_x_minimax_ate_o_fim_com_resumo_por_lado(servidor):
    servidor.padrao = _escolhe_primeiro
    orq = _orq(ControladorLLM(servidor.cliente(), "ana-1"), ControladorMinimax())
    await orq.rodar(max_lances=400)
    assert orq.estado == ENCERRADA
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
    # CA-15: no IA x IA a analise do Minimax nao vai para a LLM.
    assert all("minimax" not in servidor.textos_de(i).lower() for i in range(len(servidor.pedidos)))


async def test_ca07_llm_x_llm_usa_um_participante_por_lado(servidor):
    servidor.padrao = _escolhe_primeiro
    cliente = servidor.cliente()
    orq = _orq(ControladorLLM(cliente, "ana-1"), ControladorLLM(cliente, "bia-1"))
    await orq.rodar(max_lances=12)
    assert len(orq.lances) == 12
    modelos = [p["model"] for p in servidor.pedidos]
    assert set(modelos) == {"ana-1", "bia-1"}


async def test_ca10_hub_fora_do_ar_a_partida_continua_com_fallback(servidor):
    servidor.padrao = 503
    orq = _orq(ControladorLLM(servidor.cliente(), "ana-1"), ControladorMinimax())
    await orq.rodar(max_lances=10)
    assert len(orq.lances) == 10
    das_brancas = [x for x in orq.lances if x.cor == BRANCA]
    assert all(x.origem in ("fallback", "unico") for x in das_brancas)
    assert orq.taxa_de_fallback()["brancas"] == 1.0
    assert all(x.rotulo == "melhor" for x in das_brancas)


# --- Controle ------------------------------------------------------------------


async def test_pausar_retomar_e_encerrar():
    orq = _orq(ControladorMinimax(), ControladorMinimax())
    orq.iniciar()
    orq.pausar()
    assert orq.estado == PAUSADA
    assert await orq.passo() is None
    assert orq.lances == []
    orq.retomar()
    assert orq.estado == EM_JOGO
    assert await orq.passo() is not None
    orq.encerrar(empate=True)
    assert orq.estado == ENCERRADA
    assert orq.partida.resultado() == "empate"
    assert await orq.passo() is None


async def test_desfazer_no_orquestrador():
    orq = _orq(ControladorMinimax(), ControladorMinimax())
    await orq.rodar(max_lances=3)
    orq.desfazer()
    assert len(orq.lances) == 2 and len(orq.partida.historico) == 2
    assert orq.partida.vez == BRANCA


async def test_partida_ja_encerrada_ao_iniciar():
    orq = _orq(ControladorMinimax(), ControladorMinimax(), partida=Partida(tab=montar({"a1": "b"})))
    orq.partida.vez = PRETA
    orq.iniciar()
    assert orq.estado == ENCERRADA


# --- Tabuleiro fisico e humanos ------------------------------------------------


async def test_fora_do_modo_simulado_o_lance_da_ia_fica_pendente():
    eventos = []
    orq = _orq(
        ControladorMinimax(),
        ControladorMinimax(),
        simulado=False,
        ouvinte=lambda tipo, dados: eventos.append(tipo),
    )
    orq.iniciar()
    assert await orq.passo() is None
    assert orq.estado == AGUARDANDO_EXECUCAO
    assert orq.lances == [] and orq.pendente is not None
    assert "lance_pendente" in eventos
    assert await orq.passo() is None  # nao pede outro lance enquanto aguarda

    outro = next(x for x in orq.partida.lances_legais() if x != orq.pendente.lance)
    with pytest.raises(LanceIlegal):
        await orq.confirmar_execucao(outro)
    assert orq.estado == AGUARDANDO_EXECUCAO

    jogado = await orq.confirmar_execucao(orq.pendente.lance)
    assert jogado.origem in ("minimax", "unico") and jogado.rotulo == "melhor"
    assert orq.estado == EM_JOGO and orq.pendente is None


async def test_lance_humano_e_validado_e_julgado():
    orq = _orq(ControladorHumano(), ControladorMinimax())
    orq.iniciar()
    assert await orq.passo() is None  # humano: nada acontece sozinho
    assert orq.estado == EM_JOGO
    jogado = await orq.lance_humano(orq.partida.lance_de_texto("c3-d4"))
    assert jogado.origem == "humano" and jogado.rotulo in ROTULOS
    with pytest.raises(LanceIlegal):  # agora e a vez do Minimax
        await orq.lance_humano(orq.partida.lances_legais()[0])


async def test_modo_assistido_sugere_so_na_vez_do_assistido_com_analise(servidor):
    servidor.padrao = _escolhe_primeiro
    eventos = []
    orq = _orq(
        ControladorHumano(),
        ControladorHumano(),
        modo="assistido",
        simulado=False,
        conselheiro=ControladorLLM(servidor.cliente(), "ana-1", com_analise=True),
        cor_assistida=BRANCA,
        ouvinte=lambda tipo, dados: eventos.append((tipo, dados)),
    )
    orq.iniciar()
    sugestao = await orq.sugerir()
    assert sugestao is not None and sugestao.origem == "llm"
    assert "| minimax: " in servidor.textos_de(-1)  # CA-15: no assistido a analise vai
    tipo, dados = eventos[-1]
    assert tipo == "sugestao" and dados["minimax"]

    # CA-09: um lance diferente da sugestao e aceito normalmente.
    outro = next(x for x in orq.partida.lances_legais() if x != sugestao.lance)
    await orq.lance_humano(outro)
    assert orq.partida.vez == PRETA
    assert await orq.sugerir() is None  # vez do oponente: sem sugestao


# --- Persistencia --------------------------------------------------------------


async def test_salvar_recarregar_e_continuar(tmp_path, servidor):
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


def test_arquivo_de_versao_desconhecida_e_recusado(tmp_path):
    arquivo = tmp_path / "x.json"
    arquivo.write_text('{"versao": 99}', "utf-8")
    with pytest.raises(ValueError):
        carregar(arquivo)
