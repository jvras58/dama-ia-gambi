"""Linha de comando: `uv run dama <comando>`."""

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from .config import obter_config
from .jogo.controladores import Controlador, ControladorLLM, ControladorMinimax
from .jogo.orquestrador import ENCERRADA, Orquestrador, criar_analisador
from .jogo.persistencia import salvar
from .llm.cliente import CHAT, RESPONSES, ClienteGambi, ErroLLM
from .regras.partida import Partida
from .regras.tabuleiro import para_texto
from .regras.tipos import BRANCA, NOME_COR, PRETA

app = typer.Typer(help="Dama IA Gambi: damas pela camera, com LLMs via Gambi e Minimax.")

# Pontuacoes acima disto sao vitoria ou derrota forcada (ver minimax.busca.LIMIAR_VITORIA).
_FORCADO = 9_000


@app.callback()
def _preparar_saida() -> None:
    """Garante UTF-8 quando a saida vai para arquivo ou pipe (no Windows o padrao e cp1252)."""
    for fluxo in (sys.stdout, sys.stderr):
        if not fluxo.isatty() and hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")


def _nota(pontuacao: int) -> str:
    if pontuacao >= _FORCADO:
        return "vence"
    if pontuacao <= -_FORCADO:
        return "perde"
    return f"{pontuacao / 100:+.2f}"


def _nao_implementado(marco: str) -> None:
    typer.echo(f"Ainda nao implementado (previsto para o marco {marco}).", err=True)
    raise typer.Exit(code=1)


@app.command()
def serve() -> None:
    """Sobe o servidor HTTPS para o telefone."""
    _nao_implementado("M3")


# --- simular ---------------------------------------------------------------------


def _criar_lado(texto: str, cliente: ClienteGambi | None) -> Controlador:
    """'minimax', 'minimax:4', 'llm:*', 'llm:<participante>' ou 'llm:model:<nome>'."""
    tipo, _, resto = texto.partition(":")
    if tipo == "minimax":
        return ControladorMinimax(int(resto) if resto else None)
    if tipo == "llm":
        if cliente is None:
            raise typer.BadParameter("lado LLM exige --sala (ou DAMA_GAMBI_SALA)")
        return ControladorLLM(cliente, resto or "*")
    raise typer.BadParameter(f"lado invalido: {texto!r}. Use minimax[:prof] ou llm:<modelo>.")


def _nome_do_lado(controlador: Controlador) -> str:
    d = controlador.descricao()
    if d["tipo"] == "llm":
        return f"LLM {d['modelo']}"
    prof = d.get("profundidade")
    return f"Minimax (prof. {prof})" if prof else "Minimax"


@app.command()
def simular(
    brancas: Annotated[str, typer.Option(help="minimax[:prof] ou llm:<modelo>")] = "llm:*",
    pretas: Annotated[str, typer.Option(help="minimax[:prof] ou llm:<modelo>")] = "minimax",
    hub: Annotated[str | None, typer.Option(help="URL do hub Gambi")] = None,
    sala: Annotated[str | None, typer.Option(help="Codigo da sala Gambi")] = None,
    max_lances: Annotated[int, typer.Option(help="Para depois deste numero de lances")] = 300,
    pasta: Annotated[Path, typer.Option(help="Onde salvar a partida")] = Path("dados/partidas"),
    mostrar_tabuleiro: Annotated[bool, typer.Option(help="Imprime o tabuleiro a cada lance")] = (
        False
    ),
) -> None:
    """Roda uma partida sem camera, no terminal: LLM x LLM, LLM x Minimax ou Minimax x Minimax."""
    config = obter_config()
    hub = hub or config.gambi_hub
    sala = sala or config.gambi_sala
    precisa_llm = brancas.startswith("llm") or pretas.startswith("llm")
    if precisa_llm and not sala:
        typer.echo("Informe a sala com --sala ou DAMA_GAMBI_SALA.", err=True)
        raise typer.Exit(code=2)
    asyncio.run(_simular(brancas, pretas, hub, sala, max_lances, pasta, mostrar_tabuleiro, config))


async def _simular(brancas, pretas, hub, sala, max_lances, pasta, mostrar_tabuleiro, config):
    cliente = ClienteGambi(hub, sala, config.llm_timeout_s) if sala else None
    controladores = {BRANCA: _criar_lado(brancas, cliente), PRETA: _criar_lado(pretas, cliente)}
    for controlador in controladores.values():
        if isinstance(controlador, ControladorLLM):
            controlador.tentativas_extras = config.llm_tentativas

    arquivo = pasta / f"{datetime.now():%Y%m%d-%H%M%S}.json"

    def ouvinte(tipo: str, dados: dict) -> None:
        if tipo != "lance":
            return
        nota = _nota(dados["pontuacao"])
        linha = (
            f"{dados['numero']:>3}. {dados['cor']:<8} {dados['lance']:<14} "
            f"[{dados['origem']:<8}] juiz: {dados['rotulo']:<8} {nota}"
        )
        if dados["motivo"] and dados["origem"] in ("llm", "fallback"):
            linha += f"  | {dados['motivo'][:70]}"
        typer.echo(linha)
        if mostrar_tabuleiro:
            typer.echo(para_texto(orq.partida.tab) + "\n")

    orq = Orquestrador(
        partida=Partida(),
        controladores=controladores,
        analisador=criar_analisador(config.minimax_profundidade, config.minimax_tempo_s),
        ouvinte=ouvinte,
    )
    typer.echo(f"Brancas: {_nome_do_lado(controladores[BRANCA])}")
    typer.echo(f"Pretas:  {_nome_do_lado(controladores[PRETA])}\n")

    inicio = time.perf_counter()
    try:
        orq.iniciar()
        while orq.estado != ENCERRADA and len(orq.lances) < max_lances:
            if await orq.passo() is None:
                break
            salvar(orq, arquivo)
    finally:
        if cliente is not None:
            await cliente.fechar()

    typer.echo("\n" + para_texto(orq.partida.tab))
    resultado = orq.partida.resultado()
    typer.echo(f"\nResultado: {resultado or f'interrompida apos {len(orq.lances)} lances'}")
    typer.echo(f"Duracao: {time.perf_counter() - inicio:.0f} s")
    taxas = orq.taxa_de_fallback()
    for lado, resumo in orq.resumo_do_juiz().items():
        contagem = ", ".join(f"{n} {rotulo}" for rotulo, n in resumo.contagem.items())
        cor = BRANCA if lado == NOME_COR[BRANCA] else PRETA
        extra = ""
        if isinstance(controladores[cor], ControladorLLM):
            extra = f" | fallback em {taxas[lado]:.0%} das consultas"
        typer.echo(
            f"{lado:<8} {contagem} | perda media {resumo.perda_media / 100:.2f} pedra{extra}"
        )
    if orq.lances:
        typer.echo(f"Partida salva em {arquivo}")


# --- checar-gambi ----------------------------------------------------------------


@app.command("checar-gambi")
def checar_gambi(
    hub: Annotated[str | None, typer.Option(help="URL do hub Gambi")] = None,
    sala: Annotated[str | None, typer.Option(help="Codigo da sala Gambi")] = None,
) -> None:
    """Testa o hub Gambi, a sala e cada participante (Responses e Chat Completions)."""
    config = obter_config()
    hub = hub or config.gambi_hub
    sala = sala or config.gambi_sala
    if not sala:
        typer.echo("Informe a sala com --sala ou DAMA_GAMBI_SALA.", err=True)
        raise typer.Exit(code=2)
    if not asyncio.run(_checar(hub, sala, config.llm_timeout_s)):
        raise typer.Exit(code=1)


async def _checar(hub: str, sala: str, timeout_s: float) -> bool:
    cliente = ClienteGambi(hub, sala, timeout_s)
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
        mensagens = [{"role": "user", "content": "Responda apenas com a palavra: ok"}]
        algum = False
        for participante in participantes:
            partes = []
            for protocolo in (RESPONSES, CHAT):
                inicio = time.perf_counter()
                try:
                    texto = await cliente.completar(
                        participante, "Seja breve.", mensagens, protocolo
                    )
                    duracao = time.perf_counter() - inicio
                    partes.append(f"{protocolo}: ok em {duracao:.1f} s ({texto.strip()[:20]!r})")
                    algum = True
                except ErroLLM as erro:
                    partes.append(f"{protocolo}: FALHOU ({erro})")
            typer.echo(f"  {participante}\n    " + "\n    ".join(partes))
        return algum
    finally:
        await cliente.fechar()
