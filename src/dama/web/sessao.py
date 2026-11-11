"""Sessao de captura: quem esta conectado, quem e a camera e o que a visao viu.

A sessao liga o laco de eventos do servidor a thread da visao. Os frames chegam pelo
WebSocket da camera e vao para o `TrabalhadorDeVisao`; cada resultado volta para o laco
de eventos e e difundido a todos os clientes. O estado da calibracao mora na `Visao`,
entao um telefone que cai e reconecta continua de onde parou (RF-CAP-05).
"""

import asyncio
import contextlib
import time
from collections import deque
from typing import Final

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from dama.config import obter_config
from dama.visao.pipeline import ResultadoVisao, TrabalhadorDeVisao, Visao, cantos_de, salvar_frame
from dama.web.protocolo import (
    LEITOR,
    Alerta,
    BemVindo,
    CalibrarCores,
    Captura,
    DefinirCantos,
    InverterLados,
    LimparCantos,
    MensagemDoCliente,
    Ola,
    Papel,
    SalvarFrame,
    estado_da_visao,
)

_JANELA_DO_FPS_S: Final[float] = 3.0
_DESCONEXAO: Final[str] = "websocket.disconnect"


class Sessao:
    """Estado compartilhado por todas as conexoes de uma partida."""

    def __init__(self, visao: Visao | None = None) -> None:
        """Cria a sessao em torno de uma `Visao` (nova, se nenhuma for passada)."""
        self.visao: Visao = visao or Visao()
        self.trabalhador = TrabalhadorDeVisao(self.visao, self._ao_resultado)
        self.papeis: dict[WebSocket, Papel] = {}
        self.ultimo: ResultadoVisao | None = None
        self._laco: asyncio.AbstractEventLoop | None = None
        self._chegadas: deque[float] = deque()
        self._salvar_proximo = False

    def iniciar(self) -> None:
        """Guarda o laco de eventos atual e liga a thread da visao."""
        self._laco = asyncio.get_running_loop()
        self.trabalhador.iniciar()

    def parar(self) -> None:
        """Desliga a thread da visao."""
        self.trabalhador.parar()

    @property
    def camera(self) -> WebSocket | None:
        """A conexao que tem o papel de camera, se houver."""
        for conexao, papel in self.papeis.items():
            if papel is Papel.CAMERA:
                return conexao
        return None

    def fps(self) -> float:
        """Frames por segundo recebidos da camera nos ultimos segundos."""
        limite = time.monotonic() - _JANELA_DO_FPS_S
        while self._chegadas and self._chegadas[0] < limite:
            self._chegadas.popleft()
        return len(self._chegadas) / _JANELA_DO_FPS_S

    async def atender(self, conexao: WebSocket) -> None:
        """Atende uma conexao ate ela cair: frames em binario, comandos em texto."""
        self.papeis[conexao] = Papel.ESPECTADOR
        try:
            while True:
                mensagem = await conexao.receive()
                if mensagem["type"] == _DESCONEXAO:
                    return
                dados = mensagem.get("bytes")
                texto = mensagem.get("text")
                if dados is not None:
                    self._receber_frame(conexao, dados)
                elif texto is not None:
                    await self._receber_texto(conexao, texto)
        except WebSocketDisconnect:
            return
        finally:
            self.papeis.pop(conexao, None)

    def _receber_frame(self, conexao: WebSocket, dados: bytes) -> None:
        """Entrega a visao um frame vindo da camera; frames de outros papeis sao ignorados."""
        if self.papeis.get(conexao) is not Papel.CAMERA:
            return
        self._chegadas.append(time.monotonic())
        if self._salvar_proximo:
            self._salvar_proximo = False
            salvar_frame(dados, obter_config().pasta_frames)
        self.trabalhador.enviar(dados)

    async def _receber_texto(self, conexao: WebSocket, texto: str) -> None:
        """Interpreta e executa um comando em JSON; mensagem invalida vira alerta."""
        try:
            mensagem = LEITOR.validate_json(texto)
        except ValidationError:
            await self._enviar(conexao, Alerta(mensagem="Mensagem nao reconhecida."))
            return
        if isinstance(mensagem, Ola):
            await self._apresentar(conexao, mensagem.papel)
        elif self.papeis.get(conexao) is not Papel.CAMERA:
            await self._enviar(conexao, Alerta(mensagem="So a camera pode calibrar."))
        else:
            await self._executar(conexao, mensagem)

    async def _apresentar(self, conexao: WebSocket, pedido: Papel) -> None:
        """Concede o papel pedido; a segunda camera vira espectadora (RF-CAP-06).

        O cliente recebe em seguida o ultimo estado da visao, para retomar de onde a
        partida esta.
        """
        config = obter_config()
        ocupada = self.camera not in (None, conexao)
        papel = Papel.ESPECTADOR if pedido is Papel.CAMERA and ocupada else pedido
        self.papeis[conexao] = papel
        await self._enviar(
            conexao,
            BemVindo(
                papel=papel,
                captura=Captura(
                    fps=config.captura_fps,
                    largura=config.captura_largura,
                    qualidade=config.captura_qualidade_jpeg,
                ),
                detector_de_mao=self.visao.sensor_de_mao is not None,
            ),
        )
        if papel is not pedido:
            await self._enviar(
                conexao, Alerta(mensagem="Ja ha uma camera ativa; voce entrou como espectador.")
            )
        if self.ultimo is not None:
            await self._enviar_resultado(conexao, self.ultimo)

    async def _executar(self, conexao: WebSocket, mensagem: MensagemDoCliente) -> None:
        """Executa um comando de calibracao vindo da camera."""
        if isinstance(mensagem, DefinirCantos):
            self.visao.definir_cantos(cantos_de(mensagem.pontos))
        elif isinstance(mensagem, LimparCantos):
            self.visao.limpar_cantos()
        elif isinstance(mensagem, CalibrarCores):
            self.visao.pedir_calibracao()
        elif isinstance(mensagem, InverterLados):
            self.visao.inverter_lados()
        elif isinstance(mensagem, SalvarFrame):
            self._salvar_proximo = True
            pasta = obter_config().pasta_frames
            await self._enviar(conexao, Alerta(mensagem=f"O proximo frame sera salvo em {pasta}."))

    def _ao_resultado(self, resultado: ResultadoVisao) -> None:
        """Chamado na thread da visao: agenda a difusao no laco de eventos."""
        if self._laco is not None and not self._laco.is_closed():
            asyncio.run_coroutine_threadsafe(self._difundir(resultado), self._laco)

    async def _difundir(self, resultado: ResultadoVisao) -> None:
        """Guarda o resultado e o envia a todos os clientes conectados."""
        self.ultimo = resultado
        for conexao in list(self.papeis):
            await self._enviar_resultado(conexao, resultado)

    async def _enviar_resultado(self, conexao: WebSocket, resultado: ResultadoVisao) -> None:
        """Envia a um cliente o estado da visao e, se houver, a previa do tabuleiro."""
        await self._enviar(conexao, estado_da_visao(resultado, self.fps()))
        if resultado.previa is not None:
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await conexao.send_bytes(resultado.previa)

    async def _enviar(self, conexao: WebSocket, mensagem: BaseModel) -> None:
        """Envia uma mensagem do protocolo; se a conexao ja caiu, nao faz nada."""
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await conexao.send_text(mensagem.model_dump_json())
