"""Montagem do prompt enviado a LLM.

A LLM nunca inventa um lance: recebe a lista numerada de lances legais e responde com o numero.
A analise do Minimax so entra no prompt quando `analise` e passada (modo assistido).
"""

from typing import Final

from dama.config import obter_config
from dama.minimax.analise import AnalisePosicao, Rotulo
from dama.regras.partida import Partida, Registro
from dama.regras.tabuleiro import SIMBOLO_VAZIA, SIMBOLOS, notacao, para_texto
from dama.regras.tipos import BRANCA, CORES, DAMA, NOME_COR, PEDRA, Lance, eh_dama

# Os textos do prompt sao conteudo, nao parametros: ficam aqui, junto de quem os monta.
INSTRUCOES: Final[str] = """\
Voce joga damas brasileiras num tabuleiro 8x8.

Regras essenciais:
- Pedras andam uma casa na diagonal para frente e capturam para frente e para tras.
- Damas andam e capturam a qualquer distancia na diagonal.
- A captura e obrigatoria e deve-se capturar o maior numero de pecas possivel.
- Uma pedra vira dama ao terminar o lance na ultima fileira.
- Perde quem fica sem pecas ou sem lances.

Voce recebera a posicao e uma lista numerada com TODOS os lances legais.
Escolha exatamente um lance dessa lista. Nao invente lances.

Responda em duas linhas, sem mais nada:
LANCE: <numero do lance na lista>
MOTIVO: <uma frase curta>"""

INSTRUCOES_ANALISE: Final[str] = f"""

Cada lance da lista traz a avaliacao de um motor Minimax: a nota em pedras (positiva = boa
para voce), um rotulo ({", ".join(Rotulo)}) e a continuacao prevista. Use essa
analise para fundamentar a escolha e cite-a no motivo."""


def instrucoes(com_analise: bool) -> str:
    return INSTRUCOES + (INSTRUCOES_ANALISE if com_analise else "")


def _contagem(partida: Partida) -> str:
    partes: list[str] = []
    for cor in CORES:
        pecas = [p for p in partida.tab if p * cor > 0]
        damas = sum(1 for p in pecas if eh_dama(p))
        partes.append(f"{NOME_COR[cor]} {len(pecas)} ({damas} damas)")
    return ", ".join(partes)


def _recentes(partida: Partida) -> list[Registro]:
    quantos = obter_config().llm_ultimos_lances
    return partida.historico[-quantos:] if quantos else []


def _ultimos(partida: Partida) -> str:
    recentes = _recentes(partida)
    if not recentes:
        return "nenhum (inicio da partida)"
    return " ".join(f"{NOME_COR[r.cor]}:{r.texto}" for r in recentes)


def montar_pedido(
    partida: Partida, lances: list[Lance], analise: AnalisePosicao | None = None
) -> str:
    cor = partida.vez
    meu, dele = (SIMBOLOS[PEDRA], SIMBOLOS[DAMA]), (SIMBOLOS[-PEDRA], SIMBOLOS[-DAMA])
    sentido = "sobem no diagrama (da linha 1 para a 8)"
    if cor != BRANCA:
        meu, dele = dele, meu
        sentido = "descem no diagrama (da linha 8 para a 1)"

    continuacao = obter_config().llm_lances_de_continuacao
    linhas: list[str] = [
        f"Voce joga com as {NOME_COR[cor]}: {meu[0]} = pedra, {meu[1]} = dama.",
        f"Adversario: {NOME_COR[-cor]}: {dele[0]} = pedra, {dele[1]} = dama.",
        f"As suas pedras {sentido}. '{SIMBOLO_VAZIA}' e casa vazia.",
        "",
        "Posicao:",
        para_texto(partida.tab),
        "",
        f"Pecas: {_contagem(partida)}.",
        f"Ultimos lances: {_ultimos(partida)}",
        "",
    ]
    if analise is not None:
        linhas.append(f"Lances legais (analise Minimax, profundidade {analise.profundidade}):")
    else:
        linhas.append("Lances legais:")
    for n, lance in enumerate(lances, start=1):
        texto = f"{n}. {notacao(lance)}"
        item = analise.de(lance) if analise is not None else None
        if item is not None:
            texto += f" | minimax: {item.descricao()}"
            if item.linha and continuacao:
                texto += f" | continuacao: {' '.join(item.linha[:continuacao])}"
        linhas.append(texto)
    linhas.append("")
    linhas.append(f"Escolha um numero de 1 a {len(lances)}.")
    return "\n".join(linhas)


def montar_correcao(n_lances: int) -> str:
    return (
        "Resposta invalida. Responda apenas com duas linhas:\n"
        f"LANCE: <numero de 1 a {n_lances}>\n"
        "MOTIVO: <uma frase curta>"
    )
