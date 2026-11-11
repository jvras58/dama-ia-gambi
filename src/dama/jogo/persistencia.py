"""Salvar, recarregar e exportar partidas em JSON."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ..regras.partida import Partida
from ..regras.tipos import BRANCA, NOME_COR, PRETA
from .orquestrador import LanceJogado, Orquestrador

VERSAO = 1


def para_dict(orq: Orquestrador) -> dict:
    resumo = orq.resumo_do_juiz()
    return {
        "versao": VERSAO,
        "modo": orq.modo,
        "simulado": orq.simulado,
        "estado": orq.estado,
        "lados": {NOME_COR[cor]: orq.controladores[cor].descricao() for cor in (BRANCA, PRETA)},
        "conselheiro": orq.conselheiro.descricao() if orq.conselheiro else None,
        "cor_assistida": NOME_COR[orq.cor_assistida] if orq.cor_assistida else None,
        "partida": orq.partida.para_dict(),
        "lances": [x.para_dict() for x in orq.lances],
        "juiz": {
            lado: {
                "lances": r.lances,
                "contagem": r.contagem,
                "perda_media": round(r.perda_media, 1),
            }
            for lado, r in resumo.items()
        },
        "taxa_de_fallback": orq.taxa_de_fallback(),
    }


def salvar(orq: Orquestrador, caminho: Path) -> None:
    """Grava a partida.

    Escreve num arquivo temporario e troca, para nunca deixar um JSON pela metade.
    """
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(json.dumps(para_dict(orq), ensure_ascii=False, indent=2), "utf-8")
    os.replace(temporario, caminho)


@dataclass
class PartidaSalva:
    partida: Partida
    lances: list[LanceJogado]
    dados: dict  # o JSON completo (modo, lados, conselheiro, ...)

    def descricao_do_lado(self, cor: int) -> dict:
        return self.dados["lados"][NOME_COR[cor]]


def carregar(caminho: Path) -> PartidaSalva:
    """Le uma partida salva, refazendo os lances para validar o arquivo."""
    dados = json.loads(Path(caminho).read_text("utf-8"))
    if dados.get("versao") != VERSAO:
        raise ValueError(f"versao de arquivo nao suportada: {dados.get('versao')!r}")
    return PartidaSalva(
        partida=Partida.de_dict(dados["partida"]),
        lances=[LanceJogado.de_dict(x) for x in dados["lances"]],
        dados=dados,
    )
