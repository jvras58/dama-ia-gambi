"""Busca negamax com poda alfa-beta.

- Aprofundamento iterativo com limite de profundidade e, opcionalmente, de tempo.
- Quiescencia: no horizonte, se o lado da vez tem captura (que e obrigatoria), a busca
  continua ate a posicao ficar calma.
- Tabela de transposicao valida para uma chamada de `buscar_raiz`.
- Sem limite de tempo, o resultado e deterministico.
"""

import time
from dataclasses import dataclass

from ..regras.gerador import aplicar, gerar_lances
from ..regras.tipos import Lance, Tabuleiro
from .avaliacao import avaliar

VITORIA = 10_000
INFINITO = 1_000_000
# Pontuacoes acima disto indicam vitoria forcada dentro do horizonte.
LIMIAR_VITORIA = VITORIA - 1_000

_EXATO, _INFERIOR, _SUPERIOR = 0, 1, 2
_NOS_ENTRE_RELOGIO = 512


class TempoEsgotado(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ResultadoLance:
    lance: Lance
    pontuacao: int
    linha: tuple[Lance, ...]  # resposta esperada do adversario em diante


@dataclass(frozen=True, slots=True)
class ResultadoBusca:
    lances: tuple[ResultadoLance, ...]  # do melhor para o pior
    profundidade: int  # ultima profundidade concluida
    nos: int


class _Busca:
    def __init__(self, prazo: float | None) -> None:
        self.prazo = prazo
        self.nos = 0
        self.tabela: dict[tuple[Tabuleiro, int], tuple[int, int, int, Lance | None]] = {}

    def negamax(
        self, tab: Tabuleiro, vez: int, prof: int, alfa: int, beta: int, altura: int
    ) -> tuple[int, tuple[Lance, ...]]:
        self.nos += 1
        if (
            self.prazo is not None
            and self.nos % _NOS_ENTRE_RELOGIO == 0
            and time.perf_counter() > self.prazo
        ):
            raise TempoEsgotado

        lances = gerar_lances(tab, vez)
        if not lances:
            # Sem lances: derrota. Quanto mais longe, menos ruim.
            return -(VITORIA - altura), ()

        if prof <= 0 and not lances[0].eh_captura:
            return avaliar(tab, vez), ()

        alfa_original = alfa
        chave = (tab, vez)
        preferido = None
        entrada = self.tabela.get(chave)
        if entrada is not None:
            prof_tt, valor_tt, tipo_tt, preferido = entrada
            # Posicoes de vitoria dependem da altura; nao reaproveitamos o valor.
            if prof_tt >= prof and abs(valor_tt) < LIMIAR_VITORIA:
                if tipo_tt == _EXATO:
                    return valor_tt, (preferido,) if preferido else ()
                if tipo_tt == _INFERIOR and valor_tt > alfa:
                    alfa = valor_tt
                elif tipo_tt == _SUPERIOR and valor_tt < beta:
                    beta = valor_tt
                if alfa >= beta:
                    return valor_tt, (preferido,) if preferido else ()

        if preferido is not None and preferido in lances:
            lances.remove(preferido)
            lances.insert(0, preferido)

        melhor = -INFINITO
        melhor_linha: tuple[Lance, ...] = ()
        for lance in lances:
            valor, linha = self.negamax(
                aplicar(tab, lance), -vez, prof - 1, -beta, -alfa, altura + 1
            )
            valor = -valor
            if valor > melhor:
                melhor = valor
                melhor_linha = (lance, *linha)
                if valor > alfa:
                    alfa = valor
                    if alfa >= beta:
                        break

        if melhor <= alfa_original:
            tipo = _SUPERIOR
        elif melhor >= beta:
            tipo = _INFERIOR
        else:
            tipo = _EXATO
        self.tabela[chave] = (prof, melhor, tipo, melhor_linha[0])
        return melhor, melhor_linha


def buscar_raiz(
    tab: Tabuleiro,
    vez: int,
    profundidade_max: int,
    tempo_s: float | None = None,
) -> ResultadoBusca:
    """Pontua **todos** os lances legais da posicao.

    Cada lance da raiz e buscado com janela completa, para que a pontuacao de cada um
    seja exata, e nao apenas a do melhor. Com `tempo_s`, devolve a ultima profundidade
    concluida dentro do prazo (a profundidade 1 sempre e concluida).
    """
    lances = gerar_lances(tab, vez)
    if not lances:
        return ResultadoBusca((), 0, 0)

    prazo = None if tempo_s is None else time.perf_counter() + tempo_s
    busca = _Busca(prazo=None)
    ordem = list(lances)
    resultado: list[ResultadoLance] = []
    concluida = 0

    for prof in range(1, profundidade_max + 1):
        # A primeira iteracao roda sem prazo para sempre haver uma resposta.
        busca.prazo = prazo if prof > 1 else None
        parcial = []
        try:
            for lance in ordem:
                valor, linha = busca.negamax(
                    aplicar(tab, lance), -vez, prof - 1, -INFINITO, INFINITO, 1
                )
                parcial.append(ResultadoLance(lance, -valor, linha))
        except TempoEsgotado:
            break
        # Ordenacao estavel: empates mantem a ordem do gerador.
        parcial.sort(key=lambda r: -r.pontuacao)
        resultado = parcial
        concluida = prof
        ordem = [r.lance for r in resultado]
        if prazo is not None and time.perf_counter() > prazo:
            break
        # Vitoria ou derrota forcada para todos os lances: aprofundar nao muda nada.
        if all(abs(r.pontuacao) >= LIMIAR_VITORIA for r in resultado):
            break

    return ResultadoBusca(tuple(resultado), concluida, busca.nos)
