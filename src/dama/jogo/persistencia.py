"""Salvar, recarregar e exportar partidas em JSON.

`VERSAO` e a versao do formato do arquivo. Ela muda junto com o codigo que le o
arquivo, por isso fica aqui e nao na configuracao.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict, cast

from dama.jogo.controladores import DescricaoControlador
from dama.jogo.orquestrador import Estado, LanceJogado, LanceJogadoDict, Modo, Orquestrador
from dama.minimax.analise import Rotulo
from dama.regras.partida import Partida, PartidaDict
from dama.regras.tipos import CORES, NOME_COR, Cor, Lado

VERSAO: Final[int] = 1
_SUFIXO_TEMPORARIO: Final[str] = ".tmp"
_CODIFICACAO: Final[str] = "utf-8"


class ResumoLadoDict(TypedDict):
    """Resumo do juiz para um lado, como gravado em JSON."""

    lances: int
    contagem: dict[Rotulo, int]
    perda_media: float


class PartidaSalvaDict(TypedDict):
    """Conteudo completo do arquivo de uma partida."""

    versao: int
    modo: Modo
    simulado: bool
    estado: Estado
    lados: dict[Lado, DescricaoControlador]
    conselheiro: DescricaoControlador | None
    cor_assistida: Lado | None
    partida: PartidaDict
    lances: list[LanceJogadoDict]
    juiz: dict[Lado, ResumoLadoDict]
    taxa_de_fallback: dict[Lado, float]


def para_dict(orq: Orquestrador) -> PartidaSalvaDict:
    """Monta o conteudo do arquivo a partir do estado do orquestrador."""
    return {
        "versao": VERSAO,
        "modo": orq.modo,
        "simulado": orq.simulado,
        "estado": orq.estado,
        "lados": {NOME_COR[cor]: orq.controladores[cor].descricao() for cor in CORES},
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
            for lado, r in orq.resumo_do_juiz().items()
        },
        "taxa_de_fallback": orq.taxa_de_fallback(),
    }


def salvar(orq: Orquestrador, caminho: Path) -> None:
    """Grava a partida.

    Escreve num arquivo temporario e troca, para nunca deixar um JSON pela metade.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + _SUFIXO_TEMPORARIO)
    temporario.write_text(json.dumps(para_dict(orq), ensure_ascii=False, indent=2), _CODIFICACAO)
    os.replace(temporario, caminho)


@dataclass
class PartidaSalva:
    """Uma partida lida do disco, pronta para ser continuada."""

    partida: Partida
    lances: list[LanceJogado]
    dados: PartidaSalvaDict
    """O JSON completo (modo, lados, conselheiro, ...)."""

    def descricao_do_lado(self, cor: Cor) -> DescricaoControlador:
        """Descricao do controlador que jogava com `cor`."""
        return self.dados["lados"][NOME_COR[cor]]


def carregar(caminho: Path) -> PartidaSalva:
    """Le uma partida salva, refazendo os lances para validar o arquivo.

    O JSON vem sem tipos: `Partida.de_dict` e `LanceJogado.de_dict` validam o
    conteudo ao reconstruir os objetos.
    """
    bruto: object = json.loads(caminho.read_text(_CODIFICACAO))
    versao: object = bruto.get("versao") if isinstance(bruto, dict) else None
    if versao != VERSAO:
        raise ValueError(f"versao de arquivo nao suportada: {versao!r}")
    dados = cast(PartidaSalvaDict, bruto)
    return PartidaSalva(
        partida=Partida.de_dict(dados["partida"]),
        lances=[LanceJogado.de_dict(x) for x in dados["lances"]],
        dados=dados,
    )
