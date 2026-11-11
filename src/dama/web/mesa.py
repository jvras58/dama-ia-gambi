"""Mesa de jogo: a partida jogada pela tela, sem camera.

A mesa guarda um `Orquestrador` em modo simulado. Os lances dos lados humanos chegam
em notacao e passam pelo motor de regras; os lados de IA jogam sozinhos, numa tarefa
do asyncio, ate a vez voltar para um humano. Depois de cada mudanca o estado inteiro
e difundido, entao a pagina nao guarda regra nenhuma.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from dama.config import obter_config
from dama.jogo.controladores import (
    Controlador,
    ControladorLLM,
    ControladorMinimax,
    TipoControlador,
    criar_lado,
)
from dama.jogo.orquestrador import Analisador, Estado, Modo, Orquestrador, criar_analisador
from dama.llm.cliente import ClienteGambi
from dama.regras.partida import LanceIlegal, Partida
from dama.regras.tabuleiro import N_CASAS, notacao
from dama.regras.tipos import BRANCA, NOME_COR, PRETA, Cor, Lado, Lance
from dama.web.protocolo import (
    Adversario,
    Alerta,
    Dica,
    EstadoDaPartida,
    LadosDaPartida,
    LanceDaLista,
    LanceLegal,
    OpcaoDeLado,
)

type Difusor = Callable[[BaseModel], Awaitable[None]]


class ErroDeJogo(ValueError):
    """Um comando do jogo pela tela que nao pode ser atendido; a mensagem vai ao usuario."""


def opcoes_de_lado() -> list[OpcaoDeLado]:
    """As opcoes das listas de lados, com as profundidades vindas da configuracao."""
    config = obter_config()
    minimax = TipoControlador.MINIMAX
    return [
        OpcaoDeLado(adversario=Adversario.HUMANO, valor=TipoControlador.HUMANO),
        OpcaoDeLado(
            adversario=Adversario.MINIMAX_FACIL, valor=f"{minimax}:{config.jogo_profundidade_facil}"
        ),
        OpcaoDeLado(
            adversario=Adversario.MINIMAX_MEDIO, valor=f"{minimax}:{config.jogo_profundidade_media}"
        ),
        OpcaoDeLado(adversario=Adversario.MINIMAX_FORTE, valor=minimax),
        OpcaoDeLado(adversario=Adversario.LLM, valor=TipoControlador.LLM),
    ]


def _casas_de(lance: Lance) -> list[int]:
    """Casas por onde a peca passa num lance: a origem e cada pouso."""
    return [lance.origem, *lance.caminho]


class Mesa:
    """A partida jogada pela tela e a tarefa que faz as IAs jogarem."""

    def __init__(
        self,
        difundir: Difusor,
        analisador: Analisador | None = None,
        cliente: ClienteGambi | None = None,
    ) -> None:
        """Prepara a mesa, ainda sem partida.

        `difundir` entrega uma mensagem a todos os clientes. Sem `analisador`, o juiz
        usa a profundidade e o tempo da configuracao. Sem `cliente`, um e criado se
        houver sala do Gambi configurada; sem sala, lados LLM sao recusados.
        """
        config = obter_config()
        self._difundir: Difusor = difundir
        self._analisador: Analisador = analisador or criar_analisador(
            config.minimax_profundidade, config.minimax_tempo_s
        )
        if cliente is None and config.gambi_sala:
            cliente = ClienteGambi(config.gambi_hub, config.gambi_sala, config.llm_timeout_s)
        self._cliente: ClienteGambi | None = cliente
        self.orquestrador: Orquestrador | None = None
        self._lados = LadosDaPartida(brancas=config.jogo_brancas, pretas=config.jogo_pretas)
        self._tarefa: asyncio.Task[None] | None = None
        self._pensando: bool = False
        self._dica: Dica | None = None

    async def nova(self, brancas: str, pretas: str) -> None:
        """Descarta a partida atual e comeca outra com os lados pedidos."""
        try:
            controladores: dict[Cor, Controlador] = {
                BRANCA: criar_lado(brancas, self._cliente),
                PRETA: criar_lado(pretas, self._cliente),
            }
        except ValueError as erro:
            raise ErroDeJogo(str(erro)) from erro
        await self._parar_ias()
        conselheiro: Controlador = (
            ControladorLLM(self._cliente, obter_config().gambi_modelo_padrao, com_analise=True)
            if self._cliente is not None
            else ControladorMinimax()
        )
        self.orquestrador = Orquestrador(
            partida=Partida(),
            controladores=controladores,
            analisador=self._analisador,
            modo=Modo.ASSISTIDO,
            simulado=True,
            conselheiro=conselheiro,
        )
        self._lados = LadosDaPartida(brancas=brancas.strip(), pretas=pretas.strip())
        self._dica = None
        self.orquestrador.iniciar()
        await self._continuar()

    async def jogar(self, texto: str) -> None:
        """Joga o lance do humano da vez, escrito em notacao."""
        orquestrador = self._em_andamento()
        try:
            lance = orquestrador.partida.lance_de_texto(texto)
            await orquestrador.lance_humano(lance)
        except LanceIlegal as erro:
            raise ErroDeJogo(str(erro)) from erro
        self._dica = None
        await self._continuar()

    async def desfazer(self) -> None:
        """Volta a partida ate a ultima vez em que um humano ia jogar.

        Contra uma IA, isso desfaz a resposta dela e o lance do humano. Numa partida
        sem humanos nao ha o que desfazer.
        """
        orquestrador = self._em_andamento()
        if not any(self._humano(cor) for cor in (BRANCA, PRETA)):
            raise ErroDeJogo("nao ha lado humano nesta partida")
        await self._parar_ias()
        if not orquestrador.lances:
            raise ErroDeJogo("nao ha lance para desfazer")
        orquestrador.desfazer()
        while orquestrador.lances and not self._humano(orquestrador.partida.vez):
            orquestrador.desfazer()
        self._dica = None
        await self._continuar()

    async def pedir_dica(self) -> None:
        """Pede ao conselheiro um lance para o humano da vez e difunde a sugestao."""
        orquestrador = self._em_andamento()
        vez = orquestrador.partida.vez
        if orquestrador.estado is not Estado.EM_JOGO or not self._humano(vez):
            raise ErroDeJogo("a dica so vale na vez de um humano")
        orquestrador.cor_assistida = vez
        self._pensando = True
        await self.avisar()
        try:
            decisao = await orquestrador.sugerir()
            analise = await orquestrador.analise_atual()
        finally:
            self._pensando = False
        if decisao is not None and orquestrador.partida.vez == vez:
            item = analise.de(decisao.lance)
            self._dica = Dica(
                lance=notacao(decisao.lance),
                casas=_casas_de(decisao.lance),
                origem=decisao.origem,
                motivo=decisao.motivo,
                minimax=item.descricao() if item else "",
            )
        await self.avisar()

    def estado(self) -> EstadoDaPartida:
        """O estado inteiro da partida, pronto para ir a pagina."""
        orquestrador = self.orquestrador
        gambi = self._cliente is not None
        if orquestrador is None:
            return EstadoDaPartida(
                ativa=False,
                casas=[0] * N_CASAS,
                vez=Lado.BRANCAS,
                estado=Estado.PREPARANDO,
                resultado=None,
                lados=self._lados,
                opcoes=opcoes_de_lado(),
                humano_na_vez=False,
                pensando=False,
                legais=[],
                lances=[],
                ultimo=[],
                dica=None,
                gambi=gambi,
            )
        partida = orquestrador.partida
        em_jogo = orquestrador.estado is Estado.EM_JOGO
        humano_na_vez = em_jogo and self._humano(partida.vez)
        return EstadoDaPartida(
            ativa=True,
            casas=list(partida.tab),
            vez=NOME_COR[partida.vez],
            estado=orquestrador.estado,
            resultado=partida.resultado(),
            lados=self._lados,
            opcoes=opcoes_de_lado(),
            humano_na_vez=humano_na_vez,
            pensando=self._pensando,
            legais=[
                LanceLegal(
                    texto=notacao(lance), casas=_casas_de(lance), capturas=list(lance.capturas)
                )
                for lance in (partida.lances_legais() if humano_na_vez else [])
            ],
            lances=[
                LanceDaLista(
                    numero=x.numero,
                    cor=NOME_COR[x.cor],
                    lance=x.texto,
                    origem=x.origem,
                    motivo=x.motivo,
                    rotulo=x.rotulo,
                )
                for x in orquestrador.lances
            ],
            ultimo=_casas_de(partida.historico[-1].lance) if partida.historico else [],
            dica=self._dica,
            gambi=gambi,
        )

    async def avisar(self) -> None:
        """Difunde o estado atual a todos os clientes."""
        await self._difundir(self.estado())

    async def parar(self) -> None:
        """Interrompe as IAs e fecha o cliente do Gambi; chamado na parada do servidor."""
        await self._parar_ias()
        if self._cliente is not None:
            await self._cliente.fechar()

    def _em_andamento(self) -> Orquestrador:
        """O orquestrador da partida atual; `ErroDeJogo` se nenhuma foi criada."""
        if self.orquestrador is None:
            raise ErroDeJogo("nenhuma partida em andamento; comece uma nova")
        return self.orquestrador

    def _humano(self, cor: Cor) -> bool:
        """Diz se o lado `cor` da partida atual e controlado por um humano."""
        orquestrador = self.orquestrador
        return (
            orquestrador is not None
            and orquestrador.controladores[cor].tipo is TipoControlador.HUMANO
        )

    async def _continuar(self) -> None:
        """Difunde o estado e liga a tarefa que joga pelos lados de IA."""
        await self.avisar()
        self._tarefa = asyncio.create_task(self._rodar_ias())

    async def _parar_ias(self) -> None:
        """Cancela a tarefa das IAs e espera ela terminar."""
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None and not tarefa.done():
            tarefa.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tarefa
        self._pensando = False

    async def _rodar_ias(self) -> None:
        """Joga pelos lados de IA ate a vez ser de um humano ou a partida acabar.

        Ao parar na vez de um humano, deixa a analise do juiz calculada, para o lance
        dele ser rotulado sem espera. Uma falha inesperada de um controlador vira
        alerta e a partida fica parada, sem derrubar o servidor.
        """
        orquestrador = self.orquestrador
        if orquestrador is None:
            return
        pausa = obter_config().jogo_pausa_entre_lances_s
        try:
            while orquestrador.estado is Estado.EM_JOGO and not self._humano(
                orquestrador.partida.vez
            ):
                self._pensando = True
                await self.avisar()
                if await orquestrador.passo() is None:
                    break
                self._pensando = False
                await self.avisar()
                await asyncio.sleep(pausa)
            self._pensando = False
            await self.avisar()
            if orquestrador.estado is Estado.EM_JOGO:
                await orquestrador.analise_atual()
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            self._pensando = False
            await self._difundir(Alerta(mensagem=f"A IA nao conseguiu jogar: {erro}"))
            await self.avisar()
