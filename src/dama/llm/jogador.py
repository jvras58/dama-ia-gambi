"""Pede um lance a LLM, com novas tentativas e fallback para o Minimax.

Garantia: o lance devolvido e sempre um dos lances legais da posicao.
"""

import asyncio
import time
from dataclasses import dataclass, field

from ..minimax.analise import AnalisePosicao
from ..regras.partida import Partida
from ..regras.tabuleiro import notacao
from ..regras.tipos import Lance
from .cliente import OCUPADO, ClienteGambi, ErroLLM
from .parser import extrair_lance, extrair_motivo
from .prompt import instrucoes, montar_correcao, montar_pedido

ORIGEM_LLM = "llm"
ORIGEM_FALLBACK = "fallback"
ORIGEM_UNICO = "unico"
ORIGEM_MINIMAX = "minimax"


@dataclass
class RegistroLLM:
    """Tudo o que aconteceu numa consulta a LLM (RF-LLM-10)."""

    participante: str
    com_analise: bool
    prompt: str = ""
    respostas: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    chamadas: int = 0
    latencia_s: float = 0.0
    lance: str = ""
    seguiu_minimax: bool | None = None

    def para_dict(self) -> dict:
        return {
            "participante": self.participante,
            "com_analise": self.com_analise,
            "prompt": self.prompt,
            "respostas": self.respostas,
            "erros": self.erros,
            "chamadas": self.chamadas,
            "latencia_s": round(self.latencia_s, 3),
            "lance": self.lance,
            "seguiu_minimax": self.seguiu_minimax,
        }


@dataclass
class Decisao:
    lance: Lance
    origem: str  # llm | fallback | unico | minimax
    motivo: str = ""
    registro: RegistroLLM | None = None


async def escolher_lance(
    cliente: ClienteGambi,
    modelo: str,
    partida: Partida,
    analise: AnalisePosicao,
    com_analise: bool = False,
    tentativas_extras: int = 2,
    espera_ocupado_s: float = 2.0,
) -> Decisao:
    """Consulta a LLM sobre a posicao atual de `partida`.

    `analise` e a analise Minimax da posicao: serve de fallback e, se `com_analise`,
    vai tambem no prompt.
    """
    lances = partida.lances_legais()
    if not lances:
        raise ValueError("a posicao nao tem lances legais")
    registro = RegistroLLM(participante=modelo, com_analise=com_analise)
    melhor = analise.melhor.lance if analise.melhor else lances[0]

    def concluir(lance: Lance, origem: str, motivo: str) -> Decisao:
        registro.lance = notacao(lance)
        registro.seguiu_minimax = lance == melhor
        return Decisao(lance, origem, motivo, registro)

    if len(lances) == 1:
        return concluir(lances[0], ORIGEM_UNICO, "unico lance legal")

    textos = [notacao(lance) for lance in lances]
    sistema = instrucoes(com_analise)
    pedido = montar_pedido(partida, lances, analise if com_analise else None)
    registro.prompt = f"{sistema}\n\n{pedido}"
    mensagens = [{"role": "user", "content": pedido}]

    inicio = time.perf_counter()
    try:
        for _ in range(1 + tentativas_extras):
            registro.chamadas += 1
            try:
                resposta = await cliente.completar(modelo, sistema, mensagens)
            except ErroLLM as erro:
                registro.erros.append(str(erro))
                if erro.tipo != OCUPADO:
                    break
                await asyncio.sleep(espera_ocupado_s)
                continue
            registro.respostas.append(resposta)
            escolhido = extrair_lance(resposta, textos)
            if escolhido is not None:
                return concluir(lances[escolhido], ORIGEM_LLM, extrair_motivo(resposta))
            registro.erros.append("resposta sem lance valido")
            mensagens = [
                *mensagens,
                {"role": "assistant", "content": resposta},
                {"role": "user", "content": montar_correcao(len(lances))},
            ]
    finally:
        registro.latencia_s = time.perf_counter() - inicio

    causa = registro.erros[-1] if registro.erros else "sem resposta"
    return concluir(melhor, ORIGEM_FALLBACK, f"fallback do Minimax ({causa})")
