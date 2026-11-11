"""Mensagens trocadas pelo WebSocket entre o telefone e o servidor.

Mensagens de texto sao JSON com o campo `tipo`. Mensagens binarias carregam imagens:
do telefone para o servidor, um frame JPEG da camera; do servidor para o telefone, a
previa JPEG do tabuleiro retificado.

Ha dois grupos de comandos: os de calibracao, que so a camera pode mandar, e os do
jogo pela tela, que qualquer cliente que nao seja espectador pode mandar.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from dama.jogo.orquestrador import Estado
from dama.llm.jogador import Origem
from dama.minimax.analise import Rotulo
from dama.regras.tipos import Lado, Resultado
from dama.visao.pipeline import ResultadoVisao, Situacao
from dama.visao.tipos import LadoDasBrancas, Ocupacao


class Papel(StrEnum):
    """O que cada dispositivo conectado faz na partida."""

    CAMERA = "camera"
    """Filma o tabuleiro e faz a calibracao; so pode haver um."""
    JOGADOR = "jogador"
    """Joga pela tela: move as pecas por toque e pede dicas."""
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


class NovaPartida(BaseModel):
    """Comeca uma partida pela tela.

    Cada lado e 'humano', 'minimax', 'minimax:<profundidade>' ou 'llm[:<participante>]'.
    """

    tipo: Literal["nova_partida"] = "nova_partida"
    brancas: str
    pretas: str


class Jogar(BaseModel):
    """Lance do humano da vez, em notacao ('c3-d4' ou 'c3xe5xg7')."""

    tipo: Literal["jogar"] = "jogar"
    lance: str


class Desfazer(BaseModel):
    """Volta a partida ate a ultima vez em que um humano ia jogar."""

    tipo: Literal["desfazer"] = "desfazer"


class PedirDica(BaseModel):
    """Pede ao conselheiro uma sugestao para o humano da vez."""

    tipo: Literal["dica"] = "dica"


type ComandoDeCalibracao = (
    DefinirCantos | LimparCantos | CalibrarCores | InverterLados | SalvarFrame
)
type ComandoDeJogo = NovaPartida | Jogar | Desfazer | PedirDica
type MensagemDoCliente = Annotated[
    Ola
    | DefinirCantos
    | LimparCantos
    | CalibrarCores
    | InverterLados
    | SalvarFrame
    | NovaPartida
    | Jogar
    | Desfazer
    | PedirDica,
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
    espelhado: bool
    casas: list[CasaLida]
    duvidosas: list[int]
    aviso: str
    duracao_ms: float
    fps: float


class Adversario(StrEnum):
    """As opcoes de quem pode controlar um lado no jogo pela tela."""

    HUMANO = "humano"
    MINIMAX_FACIL = "minimax_facil"
    MINIMAX_MEDIO = "minimax_medio"
    MINIMAX_FORTE = "minimax_forte"
    """Joga com a mesma busca do juiz."""
    LLM = "llm"
    """Um participante do Gambi; so vale com uma sala configurada."""


class OpcaoDeLado(BaseModel):
    """Uma opcao das listas de lados: o que mostrar e o texto que a escolhe."""

    adversario: Adversario
    valor: str
    """Texto mandado em `NovaPartida`, como 'minimax:2'."""


class LadosDaPartida(BaseModel):
    """Quem controla cada lado, no mesmo texto usado em `NovaPartida`."""

    brancas: str
    pretas: str


class LanceLegal(BaseModel):
    """Um lance que o humano da vez pode jogar."""

    texto: str
    casas: list[int]
    """Indices das casas por onde a peca passa: a origem e cada pouso, em ordem."""
    capturas: list[int]


class LanceDaLista(BaseModel):
    """Um lance ja jogado, como aparece na lista da pagina."""

    numero: int
    cor: Lado
    lance: str
    origem: Origem
    motivo: str
    rotulo: Rotulo | None


class Dica(BaseModel):
    """Sugestao do conselheiro para a posicao atual."""

    lance: str
    casas: list[int]
    origem: Origem
    motivo: str
    minimax: str


class EstadoDaPartida(BaseModel):
    """Tudo o que a pagina precisa para mostrar o jogo pela tela."""

    tipo: Literal["partida"] = "partida"
    ativa: bool
    """Falso enquanto nenhuma partida foi criada; os outros campos valem como vazios."""
    casas: list[int]
    """As 32 casas escuras: 0 vazia, 1 e 2 pedra e dama brancas, -1 e -2 pretas."""
    vez: Lado
    estado: Estado
    resultado: Resultado | None
    lados: LadosDaPartida
    opcoes: list[OpcaoDeLado]
    """O que as listas de lados da pagina oferecem."""
    humano_na_vez: bool
    pensando: bool
    """Uma IA esta escolhendo o lance."""
    legais: list[LanceLegal]
    """Lances do humano da vez; vazio quando a vez e de uma IA ou a partida acabou."""
    lances: list[LanceDaLista]
    ultimo: list[int]
    """Casas do ultimo lance jogado, para destacar no tabuleiro."""
    dica: Dica | None
    gambi: bool
    """Ha uma sala do Gambi configurada, entao lados LLM podem ser escolhidos."""


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
        espelhado=resultado.espelhado,
        casas=[
            CasaLida(ocupacao=x.ocupacao, confianca=round(x.confianca, 3))
            for x in resultado.leituras
        ],
        duvidosas=list(resultado.duvidosas),
        aviso=resultado.aviso,
        duracao_ms=round(resultado.duracao_ms, 1),
        fps=round(fps, 1),
    )
