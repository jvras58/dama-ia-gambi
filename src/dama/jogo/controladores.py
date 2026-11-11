"""Quem controla cada lado: uma LLM via Gambi, o Minimax ou um humano."""

import asyncio
from enum import StrEnum
from typing import ClassVar, NotRequired, Protocol, TypedDict

from dama.config import obter_config
from dama.llm.cliente import ClienteGambi
from dama.llm.jogador import Decisao, Origem, escolher_lance
from dama.minimax.analise import AnalisePosicao, analisar
from dama.regras.partida import Partida


class TipoControlador(StrEnum):
    LLM = "llm"
    MINIMAX = "minimax"
    HUMANO = "humano"


class DescricaoControlador(TypedDict):
    """Forma serializavel de um controlador, gravada junto com a partida."""

    tipo: TipoControlador
    modelo: NotRequired[str]
    com_analise: NotRequired[bool]
    profundidade: NotRequired[int | None]


class Controlador(Protocol):
    tipo: ClassVar[TipoControlador]

    def descricao(self) -> DescricaoControlador: ...

    async def escolher(self, partida: Partida, analise: AnalisePosicao) -> Decisao | None:
        """Lance escolhido para a posicao atual, ou None se o lance vem de fora (humano)."""
        ...


class ControladorLLM:
    tipo: ClassVar[TipoControlador] = TipoControlador.LLM

    def __init__(
        self,
        cliente: ClienteGambi,
        modelo: str,
        com_analise: bool = False,
        tentativas_extras: int | None = None,
        espera_ocupado_s: float | None = None,
    ) -> None:
        config = obter_config()
        self.cliente: ClienteGambi = cliente
        self.modelo: str = modelo
        self.com_analise: bool = com_analise
        self.tentativas_extras: int = (
            config.llm_tentativas if tentativas_extras is None else tentativas_extras
        )
        self.espera_ocupado_s: float = (
            config.llm_espera_ocupado_s if espera_ocupado_s is None else espera_ocupado_s
        )

    def descricao(self) -> DescricaoControlador:
        return {"tipo": self.tipo, "modelo": self.modelo, "com_analise": self.com_analise}

    async def escolher(self, partida: Partida, analise: AnalisePosicao) -> Decisao:
        return await escolher_lance(
            self.cliente,
            self.modelo,
            partida,
            analise,
            com_analise=self.com_analise,
            tentativas_extras=self.tentativas_extras,
            espera_ocupado_s=self.espera_ocupado_s,
        )


class ControladorMinimax:
    """Joga o melhor lance segundo o Minimax.

    Sem `profundidade`, usa a analise do juiz. Com ela, faz a propria busca nessa
    profundidade (um adversario mais fraco ou mais forte que o juiz).
    """

    tipo: ClassVar[TipoControlador] = TipoControlador.MINIMAX

    def __init__(self, profundidade: int | None = None) -> None:
        self.profundidade: int | None = profundidade

    def descricao(self) -> DescricaoControlador:
        return {"tipo": self.tipo, "profundidade": self.profundidade}

    async def escolher(self, partida: Partida, analise: AnalisePosicao) -> Decisao:
        if self.profundidade is not None and len(analise.lances) > 1:
            analise = await asyncio.to_thread(
                analisar, partida.tab, partida.vez, self.profundidade, None
            )
        melhor = analise.melhor
        if melhor is None:
            raise ValueError("a posicao nao tem lances legais")
        if len(analise.lances) == 1:
            return Decisao(melhor.lance, Origem.UNICO, "unico lance legal")
        return Decisao(melhor.lance, Origem.MINIMAX, f"minimax: {melhor.descricao()}")


class ControladorHumano:
    """O lance vem do tabuleiro fisico (camera) ou da interface."""

    tipo: ClassVar[TipoControlador] = TipoControlador.HUMANO

    def descricao(self) -> DescricaoControlador:
        return {"tipo": self.tipo}

    async def escolher(self, partida: Partida, analise: AnalisePosicao) -> None:
        return None


def criar_controlador(
    descricao: DescricaoControlador, cliente: ClienteGambi | None = None
) -> Controlador:
    """Recria um controlador a partir de `descricao()` (usado ao recarregar uma partida)."""
    try:
        tipo = TipoControlador(descricao["tipo"])
    except ValueError as erro:
        raise ValueError(f"tipo de controlador desconhecido: {descricao['tipo']!r}") from erro
    match tipo:
        case TipoControlador.MINIMAX:
            return ControladorMinimax(descricao.get("profundidade"))
        case TipoControlador.HUMANO:
            return ControladorHumano()
        case TipoControlador.LLM:
            if cliente is None:
                raise ValueError("controlador LLM precisa de um cliente Gambi")
            return ControladorLLM(cliente, descricao["modelo"], descricao.get("com_analise", False))
