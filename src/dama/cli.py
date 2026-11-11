"""Linha de comando: `uv run dama <comando>`."""

import asyncio
import sys
import time
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Annotated, Final, cast

import typer

from dama.config import Settings, obter_config
from dama.jogo.controladores import (
    Controlador,
    ControladorLLM,
    ControladorMinimax,
    TipoControlador,
)
from dama.jogo.orquestrador import (
    DadosEvento,
    Estado,
    Evento,
    LanceJogadoDict,
    Orquestrador,
    criar_analisador,
)
from dama.jogo.persistencia import salvar
from dama.llm.cliente import ClienteGambi, ErroLLM, Mensagem, Protocolo
from dama.llm.jogador import Origem
from dama.minimax.analise import em_pedras
from dama.regras.partida import Partida
from dama.regras.tabuleiro import para_texto
from dama.regras.tipos import BRANCA, COR_DO_LADO, PRETA, Cor

app = typer.Typer(help="Dama IA Gambi: damas pela camera, com LLMs via Gambi e Minimax.")

_CODIFICACAO: Final[str] = "utf-8"
_FORMATO_DO_ARQUIVO: Final[str] = "%Y%m%d-%H%M%S"
_SEPARADOR_DO_LADO: Final[str] = ":"
_AJUDA_LADO: Final[str] = "minimax[:prof] ou llm:<modelo>"


class Saida(IntEnum):
    """Codigos de saida do processo."""

    FALHA = 1
    USO_INCORRETO = 2


@app.callback()
def _preparar_saida() -> None:
    """Garante UTF-8 quando a saida vai para arquivo ou pipe (no Windows o padrao e cp1252)."""
    for fluxo in (sys.stdout, sys.stderr):
        if not fluxo.isatty() and hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding=_CODIFICACAO)


def _nota(pontuacao: int, config: Settings) -> str:
    """Nota de um lance para exibir: em pedras, ou 'vence'/'perde' se for forcado."""
    if pontuacao >= config.minimax_limiar_vitoria:
        return "vence"
    if pontuacao <= -config.minimax_limiar_vitoria:
        return "perde"
    return f"{em_pedras(pontuacao):+.2f}"


def _nao_implementado(marco: str) -> None:
    """Avisa que o comando ainda nao existe e encerra com falha."""
    typer.echo(f"Ainda nao implementado (previsto para o marco {marco}).", err=True)
    raise typer.Exit(code=Saida.FALHA)


@app.command()
def serve() -> None:
    """Sobe o servidor HTTPS para o telefone."""
    _nao_implementado("M3")


def _tipo_do_lado(texto: str) -> TipoControlador | None:
    """Tipo de controlador pedido em 'minimax:4' ou 'llm:x'; None se invalido."""
    nome = texto.partition(_SEPARADOR_DO_LADO)[0]
    return TipoControlador(nome) if nome in set(TipoControlador) else None


def _criar_lado(texto: str, cliente: ClienteGambi | None, config: Settings) -> Controlador:
    """'minimax', 'minimax:4', 'llm:*', 'llm:<participante>' ou 'llm:model:<nome>'."""
    resto = texto.partition(_SEPARADOR_DO_LADO)[2]
    match _tipo_do_lado(texto):
        case TipoControlador.MINIMAX:
            return ControladorMinimax(int(resto) if resto else None)
        case TipoControlador.LLM:
            if cliente is None:
                raise typer.BadParameter("lado LLM exige --sala (ou DAMA_GAMBI_SALA)")
            return ControladorLLM(cliente, resto or config.gambi_modelo_padrao)
        case _:
            raise typer.BadParameter(f"lado invalido: {texto!r}. Use {_AJUDA_LADO}.")


def _nome_do_lado(controlador: Controlador) -> str:
    """Nome de um lado para o cabecalho da simulacao."""
    if isinstance(controlador, ControladorLLM):
        return f"LLM {controlador.modelo}"
    if isinstance(controlador, ControladorMinimax) and controlador.profundidade:
        return f"Minimax (prof. {controlador.profundidade})"
    return "Minimax"


@app.command()
def simular(
    brancas: Annotated[str | None, typer.Option(help=_AJUDA_LADO)] = None,
    pretas: Annotated[str | None, typer.Option(help=_AJUDA_LADO)] = None,
    hub: Annotated[str | None, typer.Option(help="URL do hub Gambi")] = None,
    sala: Annotated[str | None, typer.Option(help="Codigo da sala Gambi")] = None,
    max_lances: Annotated[
        int | None, typer.Option(help="Para depois deste numero de lances")
    ] = None,
    pasta: Annotated[Path | None, typer.Option(help="Onde salvar a partida")] = None,
    mostrar_tabuleiro: Annotated[
        bool, typer.Option(help="Imprime o tabuleiro a cada lance")
    ] = False,
) -> None:
    """Roda uma partida sem camera, no terminal: LLM x LLM, LLM x Minimax ou Minimax x Minimax.

    O que nao for informado vem da configuracao (variaveis DAMA_* ou arquivo .env).
    """
    config = obter_config()
    lado_das_brancas = brancas or config.simulacao_brancas
    lado_das_pretas = pretas or config.simulacao_pretas
    sala_escolhida = sala or config.gambi_sala
    precisa_llm = TipoControlador.LLM in (
        _tipo_do_lado(lado_das_brancas),
        _tipo_do_lado(lado_das_pretas),
    )
    if precisa_llm and not sala_escolhida:
        typer.echo("Informe a sala com --sala ou DAMA_GAMBI_SALA.", err=True)
        raise typer.Exit(code=Saida.USO_INCORRETO)
    asyncio.run(
        _simular(
            brancas=lado_das_brancas,
            pretas=lado_das_pretas,
            hub=hub or config.gambi_hub,
            sala=sala_escolhida,
            max_lances=max_lances or config.simulacao_max_lances,
            pasta=pasta or config.pasta_partidas,
            mostrar_tabuleiro=mostrar_tabuleiro,
            config=config,
        )
    )


async def _simular(
    *,
    brancas: str,
    pretas: str,
    hub: str,
    sala: str,
    max_lances: int,
    pasta: Path,
    mostrar_tabuleiro: bool,
    config: Settings,
) -> None:
    """Joga a partida no terminal, imprimindo cada lance e o resumo final.

    A partida e gravada em `pasta` depois de cada lance.
    """
    cliente = ClienteGambi(hub, sala, config.llm_timeout_s) if sala else None
    controladores: dict[Cor, Controlador] = {
        BRANCA: _criar_lado(brancas, cliente, config),
        PRETA: _criar_lado(pretas, cliente, config),
    }
    partida = Partida()
    arquivo = pasta / f"{datetime.now():{_FORMATO_DO_ARQUIVO}}.json"

    def ouvinte(tipo: Evento, dados: DadosEvento) -> None:
        """Imprime uma linha por lance jogado; ignora os outros eventos."""
        if tipo is not Evento.LANCE:
            return
        lance = cast(LanceJogadoDict, dados)
        linha = (
            f"{lance['numero']:>3}. {lance['cor']:<8} {lance['lance']:<14} "
            f"[{lance['origem']:<8}] juiz: {lance['rotulo'] or '-':<8} "
            f"{_nota(lance['pontuacao'], config)}"
        )
        if lance["motivo"] and lance["origem"] in (Origem.LLM, Origem.FALLBACK):
            linha += f"  | {lance['motivo'][: config.simulacao_motivo_max]}"
        typer.echo(linha)
        if mostrar_tabuleiro:
            typer.echo(para_texto(partida.tab) + "\n")

    orq = Orquestrador(
        partida=partida,
        controladores=controladores,
        analisador=criar_analisador(config.minimax_profundidade, config.minimax_tempo_s),
        ouvinte=ouvinte,
    )
    typer.echo(f"Brancas: {_nome_do_lado(controladores[BRANCA])}")
    typer.echo(f"Pretas:  {_nome_do_lado(controladores[PRETA])}\n")

    inicio = time.perf_counter()
    try:
        orq.iniciar()
        while orq.estado is not Estado.ENCERRADA and len(orq.lances) < max_lances:
            if await orq.passo() is None:
                break
            salvar(orq, arquivo)
    finally:
        if cliente is not None:
            await cliente.fechar()

    typer.echo("\n" + para_texto(partida.tab))
    resultado = partida.resultado()
    typer.echo(f"\nResultado: {resultado or f'interrompida apos {len(orq.lances)} lances'}")
    typer.echo(f"Duracao: {time.perf_counter() - inicio:.0f} s")
    taxas = orq.taxa_de_fallback()
    for lado, resumo in orq.resumo_do_juiz().items():
        contagem = ", ".join(f"{n} {rotulo}" for rotulo, n in resumo.contagem.items())
        extra = ""
        if isinstance(controladores[COR_DO_LADO[lado]], ControladorLLM):
            extra = f" | fallback em {taxas[lado]:.0%} das consultas"
        typer.echo(
            f"{lado:<8} {contagem} | perda media {em_pedras(resumo.perda_media):.2f} pedra{extra}"
        )
    if orq.lances:
        typer.echo(f"Partida salva em {arquivo}")


@app.command("checar-gambi")
def checar_gambi(
    hub: Annotated[str | None, typer.Option(help="URL do hub Gambi")] = None,
    sala: Annotated[str | None, typer.Option(help="Codigo da sala Gambi")] = None,
) -> None:
    """Testa o hub Gambi, a sala e cada participante (Responses e Chat Completions)."""
    config = obter_config()
    sala_escolhida = sala or config.gambi_sala
    if not sala_escolhida:
        typer.echo("Informe a sala com --sala ou DAMA_GAMBI_SALA.", err=True)
        raise typer.Exit(code=Saida.USO_INCORRETO)
    if not asyncio.run(_checar(hub or config.gambi_hub, sala_escolhida, config)):
        raise typer.Exit(code=Saida.FALHA)


async def _checar(hub: str, sala: str, config: Settings) -> bool:
    """Lista os participantes da sala e testa cada um nos dois protocolos.

    Devolve True se ao menos uma chamada de inferencia funcionou.
    """
    cliente = ClienteGambi(hub, sala, config.llm_timeout_s)
    typer.echo(f"Hub:  {hub}\nSala: {sala}\n")
    try:
        try:
            participantes = await cliente.participantes()
        except ErroLLM as erro:
            typer.echo(f"FALHA ao listar participantes: {erro}", err=True)
            typer.echo("Confira se o hub esta no ar (gambi hub serve) e o codigo da sala.")
            return False
        if not participantes:
            typer.echo("A sala existe, mas nao ha participantes de modelo disponiveis.")
            typer.echo("Entre com um: gambi participant join --room <SALA> --model <modelo> ...")
            return False

        typer.echo(f"{len(participantes)} participante(s) disponivel(is):")
        mensagens: list[Mensagem] = [
            {"role": "user", "content": "Responda apenas com a palavra: ok"}
        ]
        algum = False
        for participante in participantes:
            partes: list[str] = []
            for protocolo in Protocolo:
                inicio = time.perf_counter()
                try:
                    texto = await cliente.completar(
                        participante, "Seja breve.", mensagens, protocolo
                    )
                    duracao = time.perf_counter() - inicio
                    amostra = texto.strip()[: config.checagem_amostra_max]
                    partes.append(f"{protocolo}: ok em {duracao:.1f} s ({amostra!r})")
                    algum = True
                except ErroLLM as erro:
                    partes.append(f"{protocolo}: FALHOU ({erro})")
            typer.echo(f"  {participante}\n    " + "\n    ".join(partes))
        return algum
    finally:
        await cliente.fechar()
