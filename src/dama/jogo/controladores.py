"""Quem controla cada lado: uma LLM via Gambi, o Minimax ou um humano."""

import asyncio
from typing import Protocol

from ..llm.cliente import ClienteGambi
from ..llm.jogador import ORIGEM_MINIMAX, ORIGEM_UNICO, Decisao, escolher_lance
from ..minimax.analise import AnalisePosicao, analisar
from ..regras.partida import Partida

TIPO_LLM = "llm"
TIPO_MINIMAX = "minimax"
TIPO_HUMANO = "humano"


class Controlador(Protocol):
    tipo: str

    def descricao(self) -> dict: ...

    async def escolher(self, partida: Partida, analise: AnalisePosicao) -> Decisao | None:
        """Lance escolhido para a posicao atual, ou None se o lance vem de fora (humano)."""
        ...


class ControladorLLM:
    tipo = TIPO_LLM

    def __init__(
        self,
        cliente: ClienteGambi,
        modelo: str,
        com_analise: bool = False,
        tentativas_extras: int = 2,
        espera_ocupado_s: float = 2.0,
    ) -> None:
        self.cliente = cliente
        self.modelo = modelo
        self.com_analise = com_analise
        self.tentativas_extras = tentativas_extras
        self.espera_ocupado_s = espera_ocupado_s

    def descricao(self) -> dict:
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

    tipo = TIPO_MINIMAX

    def __init__(self, profundidade: int | None = None) -> None:
        self.profundidade = profundidade

    def descricao(self) -> dict:
        return {"tipo": self.tipo, "profundidade": self.profundidade}

    async def escolher(self, partida: Partida, analise: AnalisePosicao) -> Decisao:
        if analise.melhor is None:
            raise ValueError("a posicao nao tem lances legais")
        if self.profundidade is not None and len(analise.lances) > 1:
            analise = await asyncio.to_thread(
                analisar, partida.tab, partida.vez, self.profundidade, None
            )
        if len(analise.lances) == 1:
            return Decisao(analise.melhor.lance, ORIGEM_UNICO, "unico lance legal")
        return Decisao(
            analise.melhor.lance, ORIGEM_MINIMAX, f"minimax: {analise.melhor.descricao()}"
        )


class ControladorHumano:
    """O lance vem do tabuleiro fisico (camera) ou da interface."""

    tipo = TIPO_HUMANO

    def descricao(self) -> dict:
        return {"tipo": self.tipo}

    async def escolher(self, partida: Partida, analise: AnalisePosicao) -> None:
        return None


def criar_controlador(descricao: dict, cliente: ClienteGambi | None = None) -> Controlador:
    """Recria um controlador a partir de `descricao()` (usado ao recarregar uma partida)."""
    tipo = descricao["tipo"]
    if tipo == TIPO_MINIMAX:
        return ControladorMinimax(descricao.get("profundidade"))
    if tipo == TIPO_HUMANO:
        return ControladorHumano()
    if tipo == TIPO_LLM:
        if cliente is None:
            raise ValueError("controlador LLM precisa de um cliente Gambi")
        return ControladorLLM(cliente, descricao["modelo"], descricao.get("com_analise", False))
    raise ValueError(f"tipo de controlador desconhecido: {tipo!r}")
