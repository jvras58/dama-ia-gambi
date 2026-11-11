"""Maquina de estados da partida.

A cada turno:
1. o juiz (Minimax) analisa a posicao;
2. o controlador do lado da vez escolhe um lance, ou o lance vem de fora (humano/camera);
3. o lance e aplicado, rotulado pelo juiz e registrado.

No modo simulado, o lance de uma IA e aplicado na hora. Fora dele, fica pendente ate que
`confirmar_execucao` informe que o tabuleiro fisico reflete o lance.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import Executor
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self, TypedDict

from dama.jogo.controladores import Controlador, TipoControlador
from dama.llm.jogador import Decisao, Origem, RegistroLLMDict
from dama.minimax.analise import (
    AnalisePosicao,
    Julgamento,
    ResumoLado,
    Rotulo,
    analisar,
    resumir,
)
from dama.regras.partida import LanceIlegal, Partida
from dama.regras.tabuleiro import notacao
from dama.regras.tipos import COR_DO_LADO, CORES, NOME_COR, Cor, Lado, Lance, Resultado


class Estado(StrEnum):
    """Estados da maquina de estados da partida."""

    PREPARANDO = "preparando"
    EM_JOGO = "em_jogo"
    AGUARDANDO_EXECUCAO = "aguardando_execucao"
    PAUSADA = "pausada"
    ENCERRADA = "encerrada"


class Modo(StrEnum):
    """Modos de jogo."""

    IA_X_IA = "ia_x_ia"
    ASSISTIDO = "assistido"


class Evento(StrEnum):
    """Tipos de aviso que o orquestrador manda ao ouvinte."""

    ESTADO = "estado"
    LANCE = "lance"
    LANCE_PENDENTE = "lance_pendente"
    SUGESTAO = "sugestao"


class LanceJogadoDict(TypedDict):
    """Forma serializavel de `LanceJogado`; tambem e o dado do evento LANCE."""

    numero: int
    cor: Lado
    lance: str
    origem: Origem
    motivo: str
    rotulo: Rotulo | None
    pontuacao: int
    perda: int
    registro_llm: RegistroLLMDict | None


class DadosEstado(TypedDict):
    """Dado do evento ESTADO: o novo estado e o resultado, se a partida acabou."""

    estado: Estado
    resultado: Resultado | None


class DadosLancePendente(TypedDict):
    """Dado do evento LANCE_PENDENTE: o lance que falta executar no tabuleiro."""

    cor: Lado
    lance: str
    origem: Origem
    motivo: str


class DadosSugestao(TypedDict):
    """Dado do evento SUGESTAO: o lance sugerido e a nota do Minimax para ele."""

    lance: str
    origem: Origem
    motivo: str
    minimax: str


type DadosEvento = LanceJogadoDict | DadosEstado | DadosLancePendente | DadosSugestao
type Analisador = Callable[[Partida], Awaitable[AnalisePosicao]]
type Ouvinte = Callable[[Evento, DadosEvento], None]


def criar_analisador(
    profundidade: int, tempo_s: float | None, executor: Executor | None = None
) -> Analisador:
    """Analisador que roda o Minimax fora do laco de eventos.

    Com `executor=None` usa a thread padrao do asyncio; o servidor web passa um
    ProcessPoolExecutor para nao disputar a CPU com a visao.
    """

    async def analisador(partida: Partida) -> AnalisePosicao:
        """Analisa a posicao atual de `partida` no executor."""
        laco = asyncio.get_running_loop()
        return await laco.run_in_executor(
            executor, analisar, partida.tab, partida.vez, profundidade, tempo_s
        )

    return analisador


@dataclass
class LanceJogado:
    """Um lance ja aplicado, com a origem e o julgamento do juiz."""

    numero: int
    cor: Cor
    texto: str
    origem: Origem
    motivo: str
    rotulo: Rotulo | None
    """None se o lance nao foi analisado pelo juiz."""
    pontuacao: int
    perda: int
    registro_llm: RegistroLLMDict | None = None

    def para_dict(self) -> LanceJogadoDict:
        """Converte para a forma gravada em JSON."""
        return {
            "numero": self.numero,
            "cor": NOME_COR[self.cor],
            "lance": self.texto,
            "origem": self.origem,
            "motivo": self.motivo,
            "rotulo": self.rotulo,
            "pontuacao": self.pontuacao,
            "perda": self.perda,
            "registro_llm": self.registro_llm,
        }

    @classmethod
    def de_dict(cls, dados: LanceJogadoDict) -> Self:
        """Reconstroi a partir da forma gravada em JSON."""
        rotulo = dados["rotulo"]
        return cls(
            numero=dados["numero"],
            cor=COR_DO_LADO[Lado(dados["cor"])],
            texto=dados["lance"],
            origem=Origem(dados["origem"]),
            motivo=dados["motivo"],
            rotulo=Rotulo(rotulo) if rotulo else None,
            pontuacao=dados["pontuacao"],
            perda=dados["perda"],
            registro_llm=dados.get("registro_llm"),
        )


@dataclass
class Orquestrador:
    """Conduz uma partida: pede lances, aplica, julga e avisa o ouvinte.

    `conselheiro` e `cor_assistida` so sao usados no modo assistido.
    """

    partida: Partida
    controladores: Mapping[Cor, Controlador]
    analisador: Analisador
    modo: Modo = Modo.IA_X_IA
    simulado: bool = True
    conselheiro: Controlador | None = None
    """Modo assistido: sugere lances."""
    cor_assistida: Cor | None = None
    ouvinte: Ouvinte | None = None
    lances: list[LanceJogado] = field(default_factory=list)
    estado: Estado = Estado.PREPARANDO
    pendente: Decisao | None = None
    _analise: AnalisePosicao | None = field(default=None, repr=False)
    _estado_antes_da_pausa: Estado = field(default=Estado.EM_JOGO, repr=False)

    def iniciar(self) -> None:
        """Sai de PREPARANDO para EM_JOGO (ou ENCERRADA, se nao ha o que jogar)."""
        if self.estado is Estado.PREPARANDO:
            self._mudar_estado(Estado.ENCERRADA if self.partida.encerrada() else Estado.EM_JOGO)

    def pausar(self) -> None:
        """Pausa a partida, lembrando o estado em que ela estava."""
        if self.estado in (Estado.EM_JOGO, Estado.AGUARDANDO_EXECUCAO):
            self._estado_antes_da_pausa = self.estado
            self._mudar_estado(Estado.PAUSADA)

    def retomar(self) -> None:
        """Volta ao estado anterior a pausa."""
        if self.estado is Estado.PAUSADA:
            self._mudar_estado(self._estado_antes_da_pausa)

    def encerrar(self, empate: bool = False) -> None:
        """Encerra a partida; com `empate=True`, registra empate por acordo."""
        if empate:
            self.partida.empate_por_acordo = True
        self.pendente = None
        self._mudar_estado(Estado.ENCERRADA)

    async def analise_atual(self) -> AnalisePosicao:
        """Analise do juiz para a posicao da vez (calculada uma vez por posicao)."""
        if self._analise is None:
            self._analise = await self.analisador(self.partida)
        return self._analise

    async def passo(self) -> LanceJogado | None:
        """Avanca um turno de IA. Devolve o lance aplicado, ou None se nada foi aplicado.

        Nao faz nada se a partida nao esta em jogo ou se o lado da vez e humano.

        O estado e conferido de novo depois da escolha, porque a partida pode ter sido
        pausada ou encerrada enquanto o controlador pensava.
        """
        if self.estado is not Estado.EM_JOGO:
            return None
        controlador = self.controladores[self.partida.vez]
        analise = await self.analise_atual()
        decisao = await controlador.escolher(self.partida, analise)
        if decisao is None or not self._em_jogo():
            return None
        if self.simulado:
            return self._aplicar(decisao.lance, decisao)
        self.pendente = decisao
        self._mudar_estado(Estado.AGUARDANDO_EXECUCAO)
        self._emitir(
            Evento.LANCE_PENDENTE,
            {
                "cor": NOME_COR[self.partida.vez],
                "lance": notacao(decisao.lance),
                "origem": decisao.origem,
                "motivo": decisao.motivo,
            },
        )
        return None

    async def confirmar_execucao(self, lance: Lance) -> LanceJogado:
        """O tabuleiro fisico mostra `lance`; so vale se for o lance pendente."""
        if self.estado is not Estado.AGUARDANDO_EXECUCAO or self.pendente is None:
            raise LanceIlegal("nao ha lance pendente de execucao")
        if lance != self.pendente.lance:
            raise LanceIlegal(
                f"esperado {notacao(self.pendente.lance)}, executado {notacao(lance)}"
            )
        decisao, self.pendente = self.pendente, None
        self.estado = Estado.EM_JOGO
        await self.analise_atual()
        return self._aplicar(lance, decisao)

    async def lance_humano(self, lance: Lance) -> LanceJogado:
        """Lance vindo de fora (camera ou interface) para um lado humano."""
        if self.estado is not Estado.EM_JOGO:
            raise LanceIlegal(f"a partida nao esta em jogo ({self.estado})")
        if self.controladores[self.partida.vez].tipo is not TipoControlador.HUMANO:
            raise LanceIlegal(f"o lado das {NOME_COR[self.partida.vez]} nao e humano")
        if lance not in self.partida.lances_legais():
            raise LanceIlegal(f"lance ilegal: {notacao(lance)}")
        await self.analise_atual()
        return self._aplicar(lance, None)

    async def sugerir(self) -> Decisao | None:
        """Sugestao do conselheiro para o jogador assistido, se for a vez dele."""
        if (
            self.conselheiro is None
            or self.estado is not Estado.EM_JOGO
            or self.partida.vez != self.cor_assistida
        ):
            return None
        analise = await self.analise_atual()
        decisao = await self.conselheiro.escolher(self.partida, analise)
        if decisao is not None:
            item = analise.de(decisao.lance)
            self._emitir(
                Evento.SUGESTAO,
                {
                    "lance": notacao(decisao.lance),
                    "origem": decisao.origem,
                    "motivo": decisao.motivo,
                    "minimax": item.descricao() if item else "",
                },
            )
        return decisao

    async def rodar(self, max_lances: int | None = None) -> None:
        """Joga ate o fim (ou ate `max_lances`), enquanto os lados forem IAs simuladas."""
        self.iniciar()
        jogados = 0
        while self._em_jogo() and (max_lances is None or jogados < max_lances):
            if await self.passo() is None:
                break
            jogados += 1

    def desfazer(self) -> None:
        """Desfaz o ultimo lance e volta a EM_JOGO."""
        self.partida.desfazer()
        if self.lances:
            self.lances.pop()
        self.pendente = None
        self._analise = None
        self._mudar_estado(Estado.EM_JOGO)

    def resumo_do_juiz(self) -> dict[Lado, ResumoLado]:
        """Contagem de rotulos e perda media de cada lado."""
        return resumir(
            Julgamento(x.cor, x.rotulo, x.perda) for x in self.lances if x.rotulo is not None
        )

    def taxa_de_fallback(self) -> dict[Lado, float]:
        """Fracao das consultas a LLM, por lado, que terminou em fallback do Minimax."""
        taxas: dict[Lado, float] = {}
        for cor in CORES:
            consultas = [
                x for x in self.lances if x.cor == cor and x.origem in (Origem.LLM, Origem.FALLBACK)
            ]
            falhas = sum(1 for x in consultas if x.origem is Origem.FALLBACK)
            taxas[NOME_COR[cor]] = falhas / len(consultas) if consultas else 0.0
        return taxas

    def _em_jogo(self) -> bool:
        """Diz se a partida esta em jogo neste instante."""
        return self.estado is Estado.EM_JOGO

    def _aplicar(self, lance: Lance, decisao: Decisao | None) -> LanceJogado:
        """Aplica o lance, registra com o julgamento do juiz e avisa o ouvinte.

        `decisao` e None quando o lance veio de um humano.
        """
        analise = self._analise
        item = analise.de(lance) if analise else None
        cor = self.partida.vez
        registro = self.partida.jogar(lance)
        jogado = LanceJogado(
            numero=len(self.partida.historico),
            cor=cor,
            texto=registro.texto,
            origem=decisao.origem if decisao else Origem.HUMANO,
            motivo=decisao.motivo if decisao else "",
            rotulo=item.rotulo if item else None,
            pontuacao=item.pontuacao if item else 0,
            perda=item.perda if item else 0,
            registro_llm=decisao.registro.para_dict() if decisao and decisao.registro else None,
        )
        self.lances.append(jogado)
        self._analise = None
        self._emitir(Evento.LANCE, jogado.para_dict())
        if self.partida.encerrada():
            self._mudar_estado(Estado.ENCERRADA)
        return jogado

    def _mudar_estado(self, novo: Estado) -> None:
        """Troca o estado e avisa o ouvinte, se houve mudanca."""
        if novo is not self.estado:
            self.estado = novo
            self._emitir(Evento.ESTADO, {"estado": novo, "resultado": self.partida.resultado()})

    def _emitir(self, tipo: Evento, dados: DadosEvento) -> None:
        """Entrega um evento ao ouvinte, se houver um."""
        if self.ouvinte is not None:
            self.ouvinte(tipo, dados)
