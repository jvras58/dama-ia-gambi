"""Aplicacao web: a pagina do telefone, a rota de saude e o WebSocket.

A pagina e seus arquivos (HTML, JavaScript e CSS) ficam em `web/static/` e sao servidos
pelo proprio servidor, sem depender de nada de fora da rede local.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final, TypedDict

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from dama.visao.pipeline import Situacao
from dama.web.sessao import Sessao

PASTA_ESTATICA: Final[Path] = Path(__file__).parent / "static"
_PAGINA: Final[str] = "index.html"
_CABECALHO_DE_CACHE: Final[str] = "Cache-Control"
_REVALIDAR_SEMPRE: Final[str] = "no-cache"


class Saude(TypedDict):
    """Resposta da rota de saude."""

    ok: bool
    conexoes: int
    camera_ativa: bool
    fps: float
    situacao: Situacao | None
    frames_processados: int
    frames_descartados: int


def criar_app(sessao: Sessao | None = None) -> FastAPI:
    """Monta a aplicacao em torno de uma sessao (nova, se nenhuma for passada).

    A thread da visao liga quando o servidor sobe e desliga quando ele para.
    """
    sessao_ativa = sessao or Sessao()

    @asynccontextmanager
    async def ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
        """Liga a sessao na subida do servidor e desliga na parada."""
        sessao_ativa.iniciar()
        try:
            yield
        finally:
            await sessao_ativa.parar()

    app = FastAPI(title="Dama IA Gambi", lifespan=ciclo_de_vida)
    app.state.sessao = sessao_ativa

    @app.middleware("http")
    async def sem_cache(pedido: Request, seguinte: RequestResponseEndpoint) -> Response:
        """Manda o navegador revalidar tudo, para o telefone nunca usar uma pagina velha."""
        resposta = await seguinte(pedido)
        resposta.headers[_CABECALHO_DE_CACHE] = _REVALIDAR_SEMPRE
        return resposta

    @app.get("/", response_class=FileResponse)
    async def pagina() -> FileResponse:
        """Pagina aberta no telefone."""
        return FileResponse(PASTA_ESTATICA / _PAGINA)

    @app.get("/api/saude")
    async def saude() -> Saude:
        """Estado do servidor, para conferir se a camera esta chegando."""
        ultimo = sessao_ativa.ultimo
        return {
            "ok": True,
            "conexoes": len(sessao_ativa.papeis),
            "camera_ativa": sessao_ativa.camera is not None,
            "fps": round(sessao_ativa.fps(), 1),
            "situacao": ultimo.situacao if ultimo else None,
            "frames_processados": sessao_ativa.trabalhador.processados,
            "frames_descartados": sessao_ativa.trabalhador.descartados,
        }

    @app.websocket("/ws")
    async def ws(conexao: WebSocket) -> None:
        """Canal de frames e comandos de cada dispositivo."""
        await conexao.accept()
        await sessao_ativa.atender(conexao)

    app.mount("/static", StaticFiles(directory=PASTA_ESTATICA), name="static")
    return app
