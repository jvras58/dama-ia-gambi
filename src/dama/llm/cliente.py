"""Cliente do hub Gambi, que expoe uma API compativel com OpenAI por sala.

URL base: http://<hub>:3000/rooms/<SALA>/v1. O hub nao tem autenticacao; a chave e
ignorada. O campo `model` aceita '*' (qualquer participante), 'model:<nome>' ou o ID
de um participante.

Os codigos HTTP abaixo fazem parte do protocolo do Gambi e nao sao ajustaveis:
- `_HTTP_OCUPADO`: o participante esta atendendo outra requisicao;
- `_HTTP_INDISPONIVEL`: hub fora do ar, sala ou participante inexistente, tunel fechado;
- `_HTTP_SEM_RESPONSES`: o hub ou o participante nao oferece a Responses API.
"""

import asyncio
from collections.abc import Sequence
from enum import StrEnum
from http import HTTPStatus
from typing import Final, Literal, TypedDict

import httpx2
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.responses import EasyInputMessageParam, ResponseInputParam

from dama.config import obter_config


class Protocolo(StrEnum):
    """APIs de inferencia que o hub pode oferecer."""

    RESPONSES = "responses"
    CHAT = "chat"


class TipoErro(StrEnum):
    """Tipos de falha, usados para decidir entre tentar de novo e cair no fallback."""

    OCUPADO = "ocupado"
    """Participante atendendo outra requisicao."""
    INDISPONIVEL = "indisponivel"
    """Hub fora do ar, sala/participante inexistente, tunel fechado."""
    TEMPO = "tempo"
    OUTRO = "outro"


class Mensagem(TypedDict):
    """Uma mensagem da conversa com a LLM."""

    role: Literal["user", "assistant"]
    content: str


_HTTP_OCUPADO: Final[int] = HTTPStatus.CONFLICT
_HTTP_INDISPONIVEL: Final[frozenset[int]] = frozenset(
    {HTTPStatus.NOT_FOUND, HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE}
)
_HTTP_SEM_RESPONSES: Final[frozenset[int]] = frozenset(
    {
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.METHOD_NOT_ALLOWED,
        HTTPStatus.NOT_IMPLEMENTED,
    }
)


class ErroLLM(Exception):
    """Falha ao consultar a LLM, ja classificada em `tipo`."""

    def __init__(self, tipo: TipoErro, mensagem: str) -> None:
        """Guarda o tipo da falha e a mensagem para o registro."""
        super().__init__(mensagem)
        self.tipo = tipo


def _classificar(erro: Exception) -> ErroLLM:
    """Converte qualquer excecao da chamada num `ErroLLM` com o tipo certo."""
    if isinstance(erro, ErroLLM):
        return erro
    if isinstance(erro, (APITimeoutError, TimeoutError)):
        return ErroLLM(TipoErro.TEMPO, "a LLM nao respondeu dentro do tempo limite")
    if isinstance(erro, APIConnectionError):
        return ErroLLM(TipoErro.INDISPONIVEL, "nao foi possivel conectar ao hub Gambi")
    if isinstance(erro, APIStatusError):
        codigo = erro.status_code
        if codigo == _HTTP_OCUPADO:
            return ErroLLM(TipoErro.OCUPADO, f"participante ocupado ({codigo})")
        if codigo in _HTTP_INDISPONIVEL:
            return ErroLLM(TipoErro.INDISPONIVEL, f"hub Gambi respondeu {codigo}")
        return ErroLLM(TipoErro.OUTRO, f"hub Gambi respondeu {codigo}")
    return ErroLLM(TipoErro.OUTRO, f"{type(erro).__name__}: {erro}")


class ClienteGambi:
    """Acesso a uma sala do hub Gambi.

    `protocolo` comeca como None e e descoberto na primeira chamada que funcionar.
    """

    def __init__(
        self,
        hub: str,
        sala: str,
        timeout_s: float,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        """Prepara o cliente OpenAI apontado para a sala.

        As novas tentativas ficam desligadas no cliente (`max_retries=0`), porque quem
        decide se tenta de novo e quem chama. `http_client` serve para os testes.
        """
        self.hub: str = hub.rstrip("/")
        self.sala: str = sala
        self.timeout_s: float = timeout_s
        self.protocolo: Protocolo | None = None
        self._openai = AsyncOpenAI(
            base_url=f"{self.hub}/rooms/{sala}/v1",
            api_key=obter_config().gambi_chave_api,
            max_retries=0,
            timeout=timeout_s,
            http_client=http_client,
        )

    async def participantes(self) -> list[str]:
        """IDs dos participantes de modelo disponiveis na sala."""
        try:
            async with asyncio.timeout(self.timeout_s):
                pagina = await self._openai.models.list()
        except Exception as erro:
            raise _classificar(erro) from erro
        return [modelo.id for modelo in pagina.data]

    async def completar(
        self,
        modelo: str,
        instrucoes: str,
        mensagens: Sequence[Mensagem],
        protocolo: Protocolo | None = None,
    ) -> str:
        """Envia a conversa e devolve o texto da resposta.

        Usa a Responses API (preferida pelo Gambi). Se ela nao existir para este hub ou
        participante, usa Chat Completions e passa a usa-la nas chamadas seguintes.
        """
        escolhido = protocolo or self.protocolo
        try:
            async with asyncio.timeout(self.timeout_s):
                if escolhido is Protocolo.CHAT:
                    return await self._chat(modelo, instrucoes, mensagens)
                if escolhido is Protocolo.RESPONSES:
                    return await self._responses(modelo, instrucoes, mensagens)
                try:
                    texto = await self._responses(modelo, instrucoes, mensagens)
                    self.protocolo = Protocolo.RESPONSES
                    return texto
                except APIStatusError as erro:
                    if erro.status_code not in _HTTP_SEM_RESPONSES:
                        raise
                texto = await self._chat(modelo, instrucoes, mensagens)
                self.protocolo = Protocolo.CHAT
                return texto
        except Exception as erro:
            raise _classificar(erro) from erro

    async def _responses(self, modelo: str, instrucoes: str, mensagens: Sequence[Mensagem]) -> str:
        """Chama a Responses API e devolve o texto da resposta."""
        entrada: ResponseInputParam = [
            EasyInputMessageParam(role=m["role"], content=m["content"]) for m in mensagens
        ]
        resposta = await self._openai.responses.create(
            model=modelo, instructions=instrucoes, input=entrada
        )
        return resposta.output_text or ""

    async def _chat(self, modelo: str, instrucoes: str, mensagens: Sequence[Mensagem]) -> str:
        """Chama Chat Completions e devolve o texto da resposta."""
        conversa: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=instrucoes)
        ]
        for m in mensagens:
            if m["role"] == "user":
                conversa.append(ChatCompletionUserMessageParam(role="user", content=m["content"]))
            else:
                conversa.append(
                    ChatCompletionAssistantMessageParam(role="assistant", content=m["content"])
                )
        resposta = await self._openai.chat.completions.create(model=modelo, messages=conversa)
        return resposta.choices[0].message.content or ""

    async def fechar(self) -> None:
        """Fecha as conexoes com o hub."""
        await self._openai.close()
