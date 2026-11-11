"""Busca negamax com poda alfa-beta.

- Aprofundamento iterativo com limite de profundidade e, opcionalmente, de tempo.
- Quiescencia: no horizonte, se o lado da vez tem captura (que e obrigatoria), a busca
  continua ate a posicao ficar calma.
- Tabela de transposicao valida para uma chamada de `buscar_raiz`.
- Sem limite de tempo, o resultado e deterministico.

As pontuacoes de vitoria e a janela da busca vem da configuracao (`DAMA_MINIMAX_*`).
"""

import time
from dataclasses import dataclass
from enum import IntEnum
from typing import NamedTuple

from dama.config import obter_config
from dama.minimax.avaliacao import avaliar
from dama.regras.gerador import aplicar, gerar_lances
from dama.regras.tipos import Cor, Lance, Tabuleiro

type Linha = tuple[Lance, ...]


class _Limite(IntEnum):
    """O que o valor guardado na tabela de transposicao representa."""

    EXATO = 0
    INFERIOR = 1
    SUPERIOR = 2


class _Entrada(NamedTuple):
    """Item da tabela de transposicao: o que ja se sabe de uma posicao."""

    profundidade: int
    valor: int
    limite: _Limite
    lance: Lance


class TempoEsgotado(Exception):
    """O prazo da busca acabou no meio de uma iteracao."""


@dataclass(frozen=True, slots=True)
class ResultadoLance:
    """Pontuacao de um lance da raiz e a linha de jogo prevista depois dele."""

    lance: Lance
    pontuacao: int
    linha: Linha
    """Resposta esperada do adversario em diante."""


@dataclass(frozen=True, slots=True)
class ResultadoBusca:
    """Resultado de uma busca na raiz."""

    lances: tuple[ResultadoLance, ...]
    """Do melhor para o pior."""
    profundidade: int
    """Ultima profundidade concluida."""
    nos: int


class _Busca:
    """Estado de uma busca: prazo, contador de nos e tabela de transposicao."""

    def __init__(self, prazo: float | None) -> None:
        """Comeca a busca com a tabela vazia e os limites da configuracao."""
        config = obter_config()
        self.prazo = prazo
        self.nos = 0
        self.tabela: dict[tuple[Tabuleiro, Cor], _Entrada] = {}
        self.vitoria: int = config.minimax_pontuacao_vitoria
        self.limiar_vitoria: int = config.minimax_limiar_vitoria
        self.infinito: int = config.minimax_infinito
        self.nos_entre_relogio: int = config.minimax_nos_entre_relogio

    def negamax(
        self, tab: Tabuleiro, vez: Cor, prof: int, alfa: int, beta: int, altura: int
    ) -> tuple[int, Linha]:
        """Pontuacao da posicao para o lado `vez` e a melhor linha de jogo encontrada.

        `prof` e quanto falta aprofundar e `altura` e a distancia ate a raiz.
        - Sem lances, e derrota; quanto mais longe da raiz, menos ruim.
        - No horizonte, a busca so para se nao ha captura pendente (quiescencia).
        - Valores de vitoria dependem da altura, por isso nao sao reaproveitados da
          tabela de transposicao; o lance guardado ainda serve para ordenar.
        Levanta `TempoEsgotado` se o prazo acabar.
        """
        self.nos += 1
        if (
            self.prazo is not None
            and self.nos % self.nos_entre_relogio == 0
            and time.perf_counter() > self.prazo
        ):
            raise TempoEsgotado

        lances = gerar_lances(tab, vez)
        if not lances:
            return -(self.vitoria - altura), ()

        if prof <= 0 and not lances[0].eh_captura:
            return avaliar(tab, vez), ()

        alfa_original = alfa
        chave = (tab, vez)
        entrada = self.tabela.get(chave)
        if entrada is not None:
            if entrada.profundidade >= prof and abs(entrada.valor) < self.limiar_vitoria:
                if entrada.limite is _Limite.EXATO:
                    return entrada.valor, (entrada.lance,)
                if entrada.limite is _Limite.INFERIOR and entrada.valor > alfa:
                    alfa = entrada.valor
                elif entrada.limite is _Limite.SUPERIOR and entrada.valor < beta:
                    beta = entrada.valor
                if alfa >= beta:
                    return entrada.valor, (entrada.lance,)
            if entrada.lance in lances:
                lances.remove(entrada.lance)
                lances.insert(0, entrada.lance)

        melhor = -self.infinito
        melhor_linha: Linha = ()
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
            limite = _Limite.SUPERIOR
        elif melhor >= beta:
            limite = _Limite.INFERIOR
        else:
            limite = _Limite.EXATO
        self.tabela[chave] = _Entrada(prof, melhor, limite, melhor_linha[0])
        return melhor, melhor_linha


def buscar_raiz(
    tab: Tabuleiro,
    vez: Cor,
    profundidade_max: int,
    tempo_s: float | None = None,
) -> ResultadoBusca:
    """Pontua **todos** os lances legais da posicao.

    Cada lance da raiz e buscado com janela completa, para que a pontuacao de cada um
    seja exata, e nao apenas a do melhor. Com `tempo_s`, devolve a ultima profundidade
    concluida dentro do prazo (a profundidade 1 sempre e concluida).

    A primeira iteracao roda sem prazo, para sempre haver uma resposta. A ordenacao
    e estavel: lances empatados ficam na ordem do gerador. A busca para cedo quando
    todos os lances ja tem resultado forcado, pois aprofundar nao mudaria nada.
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
        busca.prazo = prazo if prof > 1 else None
        parcial: list[ResultadoLance] = []
        try:
            for lance in ordem:
                valor, linha = busca.negamax(
                    aplicar(tab, lance), -vez, prof - 1, -busca.infinito, busca.infinito, 1
                )
                parcial.append(ResultadoLance(lance, -valor, linha))
        except TempoEsgotado:
            break
        parcial.sort(key=lambda r: -r.pontuacao)
        resultado = parcial
        concluida = prof
        ordem = [r.lance for r in resultado]
        if prazo is not None and time.perf_counter() > prazo:
            break
        if all(abs(r.pontuacao) >= busca.limiar_vitoria for r in resultado):
            break

    return ResultadoBusca(tuple(resultado), concluida, busca.nos)
