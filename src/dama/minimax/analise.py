"""Analise de uma posicao para o juiz, o analista e o jogador Minimax."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from dama.config import obter_config
from dama.minimax.busca import buscar_raiz
from dama.regras.tabuleiro import notacao
from dama.regras.tipos import CORES, NOME_COR, Cor, Lado, Lance, Tabuleiro


class Rotulo(StrEnum):
    """Nota do juiz para um lance, pela perda em relacao ao melhor lance."""

    MELHOR = "melhor"
    BOM = "bom"
    DUVIDOSO = "duvidoso"
    ERRO = "erro"


def rotular(perda: int) -> Rotulo:
    """Rotulo de um lance que perde `perda` centesimos de pedra para o melhor."""
    config = obter_config()
    if perda <= 0:
        return Rotulo.MELHOR
    if perda <= config.juiz_limite_bom:
        return Rotulo.BOM
    if perda <= config.juiz_limite_duvidoso:
        return Rotulo.DUVIDOSO
    return Rotulo.ERRO


@dataclass(frozen=True, slots=True)
class AnaliseLance:
    """Um lance legal com a pontuacao, a perda e o rotulo dados pelo Minimax."""

    lance: Lance
    texto: str
    pontuacao: int
    """Centesimos de pedra, do ponto de vista de quem joga."""
    perda: int
    """Diferenca para o melhor lance (0 = melhor)."""
    rotulo: Rotulo
    linha: tuple[str, ...]
    """Continuacao prevista, em notacao."""
    mate_em: int | None
    """>0 vence em N lances proprios; <0 perde em N; None = sem mate a vista."""

    def descricao(self) -> str:
        """Texto curto para prompt e interface: '+0.35 (bom)' ou 'vence em 2 (melhor)'."""
        if self.mate_em is not None:
            verbo = "vence" if self.mate_em > 0 else "perde"
            valor = f"{verbo} em {abs(self.mate_em)}"
        else:
            valor = f"{em_pedras(self.pontuacao):+.2f}"
        return f"{valor} ({self.rotulo})"


@dataclass(frozen=True, slots=True)
class AnalisePosicao:
    """Todos os lances legais de uma posicao, analisados."""

    vez: Cor
    lances: tuple[AnaliseLance, ...]
    """Do melhor para o pior."""
    profundidade: int
    nos: int

    @property
    def melhor(self) -> AnaliseLance | None:
        """O lance mais bem pontuado, ou None se nao ha lances."""
        return self.lances[0] if self.lances else None

    def de(self, lance: Lance) -> AnaliseLance | None:
        """A analise de um lance especifico, ou None se ele nao e legal."""
        for item in self.lances:
            if item.lance == lance:
                return item
        return None


def em_pedras(pontuacao: float) -> float:
    """Converte a pontuacao interna (em que uma pedra vale `avaliacao_valor_pedra`)."""
    return pontuacao / obter_config().avaliacao_valor_pedra


def _mate_em(pontuacao: int) -> int | None:
    """Em quantos lances proprios a vitoria (positivo) ou a derrota (negativo) e forcada.

    Devolve None se a pontuacao nao indica resultado forcado.
    """
    config = obter_config()
    if abs(pontuacao) < config.minimax_limiar_vitoria:
        return None
    meios_lances = config.minimax_pontuacao_vitoria - abs(pontuacao)
    lances_proprios = (meios_lances + 1) // 2
    return lances_proprios if pontuacao > 0 else -lances_proprios


def analisar(
    tab: Tabuleiro,
    vez: Cor,
    profundidade: int,
    tempo_s: float | None = None,
) -> AnalisePosicao:
    """Pontua e rotula todos os lances legais de `vez` na posicao."""
    busca = buscar_raiz(tab, vez, profundidade, tempo_s)
    if not busca.lances:
        return AnalisePosicao(vez, (), 0, busca.nos)
    topo = busca.lances[0].pontuacao
    itens = tuple(
        AnaliseLance(
            lance=r.lance,
            texto=notacao(r.lance),
            pontuacao=r.pontuacao,
            perda=topo - r.pontuacao,
            rotulo=rotular(topo - r.pontuacao),
            linha=tuple(notacao(x) for x in r.linha),
            mate_em=_mate_em(r.pontuacao),
        )
        for r in busca.lances
    )
    return AnalisePosicao(vez, itens, busca.profundidade, busca.nos)


@dataclass(frozen=True, slots=True)
class Julgamento:
    """O que o juiz achou de um lance jogado."""

    cor: Cor
    rotulo: Rotulo
    perda: int


@dataclass(frozen=True, slots=True)
class ResumoLado:
    """Como um lado jogou, segundo o juiz."""

    lances: int
    contagem: dict[Rotulo, int]
    perda_media: float


def resumir(julgamentos: Iterable[Julgamento]) -> dict[Lado, ResumoLado]:
    """Resumo do juiz por lado, a partir do julgamento de cada lance jogado.

    A perda de cada lance tem um teto (`juiz_perda_maxima`), para um mate perdido
    nao distorcer a media.
    """
    todos = list(julgamentos)
    teto = obter_config().juiz_perda_maxima
    resumo: dict[Lado, ResumoLado] = {}
    for cor in CORES:
        do_lado = [j for j in todos if j.cor == cor]
        contagem = Counter(j.rotulo for j in do_lado)
        perdas = [min(j.perda, teto) for j in do_lado]
        resumo[NOME_COR[cor]] = ResumoLado(
            lances=len(do_lado),
            contagem={rotulo: contagem.get(rotulo, 0) for rotulo in Rotulo},
            perda_media=sum(perdas) / len(perdas) if perdas else 0.0,
        )
    return resumo
