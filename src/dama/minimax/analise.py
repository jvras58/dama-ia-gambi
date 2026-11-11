"""Analise de uma posicao para o juiz, o analista e o jogador Minimax."""

from collections import Counter
from dataclasses import dataclass

from ..regras.tabuleiro import notacao
from ..regras.tipos import BRANCA, NOME_COR, PRETA, Lance, Tabuleiro
from .busca import LIMIAR_VITORIA, VITORIA, buscar_raiz

MELHOR, BOM, DUVIDOSO, ERRO = "melhor", "bom", "duvidoso", "erro"
ROTULOS = (MELHOR, BOM, DUVIDOSO, ERRO)

# Perda maxima, em centesimos de pedra, para cada rotulo.
LIMITE_BOM = 30
LIMITE_DUVIDOSO = 100


def rotular(perda: int) -> str:
    if perda <= 0:
        return MELHOR
    if perda <= LIMITE_BOM:
        return BOM
    if perda <= LIMITE_DUVIDOSO:
        return DUVIDOSO
    return ERRO


@dataclass(frozen=True, slots=True)
class AnaliseLance:
    lance: Lance
    texto: str
    pontuacao: int  # centesimos de pedra, do ponto de vista de quem joga
    perda: int  # diferenca para o melhor lance (0 = melhor)
    rotulo: str
    linha: tuple[str, ...]  # continuacao prevista, em notacao
    mate_em: int | None  # >0 vence em N lances proprios; <0 perde em N; None = sem mate a vista

    def descricao(self) -> str:
        """Texto curto para prompt e interface: '+0.35 (bom)' ou 'vence em 2 (melhor)'."""
        if self.mate_em is not None:
            verbo = "vence" if self.mate_em > 0 else "perde"
            valor = f"{verbo} em {abs(self.mate_em)}"
        else:
            valor = f"{self.pontuacao / 100:+.2f}"
        return f"{valor} ({self.rotulo})"


@dataclass(frozen=True, slots=True)
class AnalisePosicao:
    vez: int
    lances: tuple[AnaliseLance, ...]  # do melhor para o pior
    profundidade: int
    nos: int

    @property
    def melhor(self) -> AnaliseLance | None:
        return self.lances[0] if self.lances else None

    def de(self, lance: Lance) -> AnaliseLance | None:
        for item in self.lances:
            if item.lance == lance:
                return item
        return None


def _mate_em(pontuacao: int) -> int | None:
    if abs(pontuacao) < LIMIAR_VITORIA:
        return None
    meios_lances = VITORIA - abs(pontuacao)
    lances_proprios = (meios_lances + 1) // 2
    return lances_proprios if pontuacao > 0 else -lances_proprios


def analisar(
    tab: Tabuleiro,
    vez: int,
    profundidade: int = 8,
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
class ResumoLado:
    lances: int
    contagem: dict[str, int]
    perda_media: float


def resumir(julgamentos: list[tuple[int, str, int]]) -> dict[str, ResumoLado]:
    """Resumo do juiz por lado, a partir de (cor, rotulo, perda) de cada lance jogado."""
    resumo = {}
    for cor in (BRANCA, PRETA):
        do_lado = [(rotulo, perda) for c, rotulo, perda in julgamentos if c == cor]
        contagem = Counter(rotulo for rotulo, _ in do_lado)
        # Mates distorcem a media; a perda de cada lance e limitada a uma dama e meia.
        perdas = [min(perda, 450) for _, perda in do_lado]
        resumo[NOME_COR[cor]] = ResumoLado(
            lances=len(do_lado),
            contagem={rotulo: contagem.get(rotulo, 0) for rotulo in ROTULOS},
            perda_media=sum(perdas) / len(perdas) if perdas else 0.0,
        )
    return resumo
