"""Mensagens trocadas pelo WebSocket entre o telefone e o servidor.

Mensagens de texto sao JSON com o campo `tipo`. Mensagens binarias carregam imagens:
do telefone para o servidor, um frame JPEG da camera; do servidor para o telefone, a
previa JPEG do tabuleiro retificado.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from dama.visao.pipeline import ResultadoVisao, Situacao
from dama.visao.tipos import LadoDasBrancas, Ocupacao


class Papel(StrEnum):
    """O que cada dispositivo conectado faz na partida."""

    CAMERA = "camera"
    """Filma o tabuleiro e faz a calibracao; so pode haver um."""
    JOGADOR = "jogador"
    """Acompanha a partida e ve as sugestoes do modo assistido."""
    ESPECTADOR = "espectador"
    """So acompanha a partida."""


class Ola(BaseModel):
    """Primeira mensagem do cliente: o papel que ele quer ter."""

    tipo: Literal["ola"] = "ola"
    papel: Papel = Papel.ESPECTADOR


class DefinirCantos(BaseModel):
    """Confirma os quatro cantos da area de jogo, em fracoes da largura e da altura."""

    tipo: Literal["cantos"] = "cantos"
    pontos: Annotated[list[tuple[float, float]], Field(min_length=4, max_length=4)]


class LimparCantos(BaseModel):
    """Descarta os cantos confirmados, para refazer a marcacao."""

    tipo: Literal["limpar_cantos"] = "limpar_cantos"


class CalibrarCores(BaseModel):
    """Pede a calibracao das cores com a posicao inicial montada."""

    tipo: Literal["calibrar_cores"] = "calibrar_cores"


class InverterLados(BaseModel):
    """Troca o lado da imagem em que ficam as brancas."""

    tipo: Literal["inverter_lados"] = "inverter_lados"


class SalvarFrame(BaseModel):
    """Pede que o proximo frame recebido seja gravado em disco."""

    tipo: Literal["salvar_frame"] = "salvar_frame"


type MensagemDoCliente = Annotated[
    Ola | DefinirCantos | LimparCantos | CalibrarCores | InverterLados | SalvarFrame,
    Field(discriminator="tipo"),
]

LEITOR: TypeAdapter[MensagemDoCliente] = TypeAdapter(MensagemDoCliente)


class Captura(BaseModel):
    """Como o telefone deve capturar e enviar os frames."""

    fps: int
    largura: int
    qualidade: float


class BemVindo(BaseModel):
    """Resposta ao `ola`: o papel concedido e os parametros de captura."""

    tipo: Literal["bem_vindo"] = "bem_vindo"
    papel: Papel
    captura: Captura
    detector_de_mao: bool


class CasaLida(BaseModel):
    """Classificacao de uma casa escura."""

    ocupacao: Ocupacao
    confianca: float


class EstadoDaVisao(BaseModel):
    """O que a visao tirou do frame mais recente."""

    tipo: Literal["visao"] = "visao"
    situacao: Situacao
    largura: int
    altura: int
    cantos: list[tuple[float, float]] | None
    cantos_sugeridos: list[tuple[float, float]] | None
    lado_das_brancas: LadoDasBrancas | None
    casas: list[CasaLida]
    duvidosas: list[int]
    aviso: str
    duracao_ms: float
    fps: float


class Alerta(BaseModel):
    """Aviso do servidor para ser mostrado ao usuario."""

    tipo: Literal["alerta"] = "alerta"
    mensagem: str


def estado_da_visao(resultado: ResultadoVisao, fps: float) -> EstadoDaVisao:
    """Converte o resultado da visao na mensagem enviada aos clientes."""
    return EstadoDaVisao(
        situacao=resultado.situacao,
        largura=resultado.largura,
        altura=resultado.altura,
        cantos=list(resultado.cantos) if resultado.cantos else None,
        cantos_sugeridos=list(resultado.cantos_sugeridos) if resultado.cantos_sugeridos else None,
        lado_das_brancas=resultado.lado_das_brancas,
        casas=[
            CasaLida(ocupacao=x.ocupacao, confianca=round(x.confianca, 3))
            for x in resultado.leituras
        ],
        duvidosas=list(resultado.duvidosas),
        aviso=resultado.aviso,
        duracao_ms=round(resultado.duracao_ms, 1),
        fps=round(fps, 1),
    )
