"""Cliente do hub Gambi, que expoe uma API compativel com OpenAI por sala.

URL base: http://<hub>:3000/rooms/<SALA>/v1. O hub nao tem autenticacao; a chave e ignorada.
O campo `model` aceita '*' (qualquer participante), 'model:<nome>' ou o ID de um participante.
"""

import asyncio

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

RESPONSES = "responses"
CHAT = "chat"

# Tipos de falha, usados para decidir entre tentar de novo e cair no fallback.
OCUPADO = "ocupado"  # 409: participante atendendo outra requisicao
INDISPONIVEL = "indisponivel"  # hub fora do ar, sala/participante inexistente, tunel fechado
TEMPO = "tempo"
OUTRO = "outro"


class ErroLLM(Exception):
    def __init__(self, tipo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.tipo = tipo


def _classificar(erro: Exception) -> ErroLLM:
    if isinstance(erro, (APITimeoutError, TimeoutError)):
        return ErroLLM(TEMPO, "a LLM nao respondeu dentro do tempo limite")
    if isinstance(erro, APIConnectionError):
        return ErroLLM(INDISPONIVEL, "nao foi possivel conectar ao hub Gambi")
    if isinstance(erro, APIStatusError):
        codigo = erro.status_code
        if codigo == 409:
            return ErroLLM(OCUPADO, "participante ocupado (409)")
        if codigo in (404, 502, 503):
            return ErroLLM(INDISPONIVEL, f"hub Gambi respondeu {codigo}")
        return ErroLLM(OUTRO, f"hub Gambi respondeu {codigo}")
    return ErroLLM(OUTRO, f"{type(erro).__name__}: {erro}")


class ClienteGambi:
    def __init__(
        self,
        hub: str,
        sala: str,
        timeout_s: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.hub = hub.rstrip("/")
        self.sala = sala
        self.timeout_s = timeout_s
        self.protocolo: str | None = None  # descoberto na primeira chamada que funcionar
        self._openai = AsyncOpenAI(
            base_url=f"{self.hub}/rooms/{sala}/v1",
            api_key="gambi",
            max_retries=0,  # as novas tentativas sao decididas por quem chama
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
        mensagens: list[dict[str, str]],
        protocolo: str | None = None,
    ) -> str:
        """Envia a conversa e devolve o texto da resposta.

        Usa a Responses API (preferida pelo Gambi). Se ela nao existir para este hub ou
        participante, usa Chat Completions e passa a usa-la nas chamadas seguintes.
        """
        escolhido = protocolo or self.protocolo
        try:
            async with asyncio.timeout(self.timeout_s):
                if escolhido == CHAT:
                    return await self._chat(modelo, instrucoes, mensagens)
                if escolhido == RESPONSES:
                    return await self._responses(modelo, instrucoes, mensagens)
                try:
                    texto = await self._responses(modelo, instrucoes, mensagens)
                    self.protocolo = RESPONSES
                    return texto
                except APIStatusError as erro:
                    if erro.status_code not in (400, 404, 405, 501):
                        raise
                texto = await self._chat(modelo, instrucoes, mensagens)
                self.protocolo = CHAT
                return texto
        except Exception as erro:
            raise _classificar(erro) from erro

    async def _responses(self, modelo: str, instrucoes: str, mensagens: list[dict]) -> str:
        resposta = await self._openai.responses.create(
            model=modelo, instructions=instrucoes, input=mensagens
        )
        return resposta.output_text or ""

    async def _chat(self, modelo: str, instrucoes: str, mensagens: list[dict]) -> str:
        resposta = await self._openai.chat.completions.create(
            model=modelo,
            messages=[{"role": "system", "content": instrucoes}, *mensagens],
        )
        return resposta.choices[0].message.content or ""

    async def fechar(self) -> None:
        await self._openai.close()
