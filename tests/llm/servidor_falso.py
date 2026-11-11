"""Servidor falso que imita a API de inferencia do Gambi (compativel com OpenAI).

Cada chamada de inferencia consome um item do roteiro:
    str             -> texto da resposta
    int             -> responde com esse codigo HTTP e corpo {"error": "..."}
    ("lento", s)    -> espera `s` segundos e responde "LANCE: 1"
    callable(texto) -> recebe o texto do ultimo pedido do usuario e devolve a resposta
Com o roteiro vazio, usa `padrao`.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dama.llm.cliente import ClienteGambi

Passo = str | int | tuple | Callable[[str], str]


@dataclass
class ServidorFalso:
    roteiro: list[Passo] = field(default_factory=list)
    padrao: Passo = "LANCE: 1\nMOTIVO: lance padrao do servidor falso."
    participantes: list[str] = field(default_factory=lambda: ["ana-1", "bia-1"])
    sem_responses: bool = False
    sala: str = "ABC123"
    pedidos: list[dict] = field(default_factory=list)  # tudo o que chegou, para inspecao

    def app(self) -> FastAPI:
        app = FastAPI()
        prefixo = "/rooms/{sala}/v1"

        @app.get(prefixo + "/models")
        async def modelos(sala: str):
            if sala != self.sala:
                return JSONResponse({"error": "room not found"}, status_code=404)
            return {
                "object": "list",
                "data": [
                    {"id": p, "object": "model", "created": 0, "owned_by": "gambi"}
                    for p in self.participantes
                ],
            }

        @app.post(prefixo + "/responses")
        async def responses(sala: str, pedido: Request):
            corpo = await pedido.json()
            if self.sem_responses:
                return JSONResponse({"error": "not found"}, status_code=404)
            self.pedidos.append({"rota": "responses", **corpo})
            ultimo = corpo["input"][-1]["content"]
            resultado = await self._proximo(sala, ultimo)
            if isinstance(resultado, JSONResponse):
                return resultado
            return {
                "id": "resp_1",
                "object": "response",
                "created_at": 0,
                "model": corpo["model"],
                "status": "completed",
                "parallel_tool_calls": True,
                "tool_choice": "auto",
                "tools": [],
                "output": [
                    {
                        "type": "message",
                        "id": "msg_1",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": resultado, "annotations": []}],
                    }
                ],
            }

        @app.post(prefixo + "/chat/completions")
        async def chat(sala: str, pedido: Request):
            corpo = await pedido.json()
            self.pedidos.append({"rota": "chat", **corpo})
            ultimo = corpo["messages"][-1]["content"]
            resultado = await self._proximo(sala, ultimo)
            if isinstance(resultado, JSONResponse):
                return resultado
            return {
                "id": "chatcmpl_1",
                "object": "chat.completion",
                "created": 0,
                "model": corpo["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": resultado},
                        "finish_reason": "stop",
                    }
                ],
            }

        return app

    async def _proximo(self, sala: str, ultimo_pedido: str) -> str | JSONResponse:
        if sala != self.sala:
            return JSONResponse({"error": "room not found"}, status_code=404)
        passo = self.roteiro.pop(0) if self.roteiro else self.padrao
        if isinstance(passo, int):
            return JSONResponse({"error": f"erro simulado {passo}"}, status_code=passo)
        if isinstance(passo, tuple):
            await asyncio.sleep(passo[1])
            return "LANCE: 1\nMOTIVO: resposta lenta."
        if callable(passo):
            return passo(ultimo_pedido)
        return passo

    def cliente(self, timeout_s: float = 5.0, sala: str | None = None) -> ClienteGambi:
        """ClienteGambi ligado a este servidor, sem abrir porta de rede."""
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app()))
        return ClienteGambi("http://falso", sala or self.sala, timeout_s, http_client=http)

    def textos_de(self, indice: int = -1) -> str:
        """Todo o texto (instrucoes + mensagens) de um pedido recebido."""
        pedido = self.pedidos[indice]
        if pedido["rota"] == "responses":
            partes = [pedido.get("instructions", "")] + [m["content"] for m in pedido["input"]]
        else:
            partes = [m["content"] for m in pedido["messages"]]
        return "\n".join(partes)
