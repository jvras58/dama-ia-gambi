"""Do frame da camera a leitura das casas.

`Visao` guarda o estado da calibracao (cantos, lado das brancas, cores aprendidas) e
processa um frame por vez. `TrabalhadorDeVisao` roda a `Visao` numa thread propria, com
uma fila de tamanho 1: se chega um frame novo antes de o anterior ser processado, o
anterior e descartado, para o atraso nunca acumular.

Os cantos trocados com o telefone sao normalizados (0 a 1 da largura e da altura do
frame), para nao depender do tamanho em que a imagem e exibida ou processada.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

import cv2
import numpy as np

from dama.config import obter_config
from dama.visao.classificador import (
    CalibracaoInvalida,
    Classificador,
    ClassificadorCor,
    lado_mais_claro,
    ocupacao_inicial,
)
from dama.visao.localizacao import espelhar, localizar_tabuleiro, orientar, reduzir, retificar
from dama.visao.tipos import Cantos, Imagem, LadoDasBrancas, LeituraCasa, Ponto

_EXTENSAO: Final[str] = ".jpg"
_INTERVALO_DE_GRAVACAO_S: Final[float] = 1.0


class Situacao(StrEnum):
    """O que a visao conseguiu fazer com um frame."""

    FRAME_INVALIDO = "frame_invalido"
    """Os bytes recebidos nao sao uma imagem."""
    SEM_CANTOS = "sem_cantos"
    """Os cantos do tabuleiro ainda nao foram confirmados."""
    SEM_CORES = "sem_cores"
    """Os cantos estao definidos, mas as cores ainda nao foram calibradas."""
    MAO = "mao"
    """Ha uma mao sobre o tabuleiro; a leitura esta suspensa."""
    LEITURA = "leitura"
    """As 32 casas foram classificadas."""


class SensorDeMao(Protocol):
    """O que a visao precisa de um detector de mao."""

    def ha_mao_sobre(self, imagem: Imagem, cantos: Cantos, instante_s: float) -> bool:
        """Diz se ha uma mao sobre o tabuleiro delimitado por `cantos`."""
        ...


@dataclass(frozen=True, slots=True)
class ResultadoVisao:
    """O que a visao tirou de um frame."""

    situacao: Situacao
    largura: int = 0
    altura: int = 0
    cantos: Cantos | None = None
    """Cantos confirmados da area de jogo, normalizados."""
    cantos_sugeridos: Cantos | None = None
    """Cantos achados automaticamente, normalizados; so vem enquanto nao ha confirmados."""
    lado_das_brancas: LadoDasBrancas | None = None
    espelhado: bool = False
    """Tabuleiro montado com casa clara a esquerda de cada jogador, lido espelhado."""
    leituras: tuple[LeituraCasa, ...] = ()
    """Classificacao das 32 casas, na ordem dos indices; vazia se nao houve leitura."""
    duvidosas: tuple[int, ...] = ()
    """Indices das casas com confianca abaixo de `visao_confianca_min`."""
    aviso: str = ""
    """Mensagem para o usuario, por exemplo o motivo de uma calibracao recusada."""
    previa: bytes | None = None
    """JPEG do tabuleiro retificado, para o telefone conferir o alinhamento."""
    duracao_ms: float = 0.0


def _normalizar(cantos: Cantos, largura: int, altura: int) -> Cantos:
    """Converte cantos em pixels para fracoes da largura e da altura."""
    p = [(x / largura, y / altura) for x, y in cantos]
    return (p[0], p[1], p[2], p[3])


def _em_pixels(cantos: Cantos, largura: int, altura: int) -> Cantos:
    """Converte cantos normalizados para pixels de uma imagem deste tamanho."""
    p = [(x * largura, y * altura) for x, y in cantos]
    return (p[0], p[1], p[2], p[3])


def decodificar(dados: bytes) -> Imagem | None:
    """Decodifica um JPEG e reduz ao tamanho de processamento; None se for invalido."""
    if not dados:
        return None
    imagem = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        return None
    return reduzir(imagem.astype(np.uint8))


def codificar_previa(retificada: Imagem) -> bytes | None:
    """JPEG reduzido do tabuleiro retificado; None se a codificacao falhar."""
    config = obter_config()
    lado = config.visao_lado_da_previa
    pequena = cv2.resize(retificada, (lado, lado), interpolation=cv2.INTER_AREA)
    ok, saida = cv2.imencode(
        _EXTENSAO, pequena, [cv2.IMWRITE_JPEG_QUALITY, config.visao_qualidade_da_previa]
    )
    return saida.tobytes() if ok else None


@dataclass
class Visao:
    """Estado da calibracao e processamento de um frame por vez.

    Os metodos que mudam a calibracao podem ser chamados de outra thread enquanto
    `processar` roda; um cadeado protege o estado.
    """

    classificador: Classificador = field(default_factory=ClassificadorCor)
    sensor_de_mao: SensorDeMao | None = None
    _cantos: Cantos | None = None
    _orientados: bool = False
    _espelhado: bool = False
    _lado_das_brancas: LadoDasBrancas = LadoDasBrancas.BAIXO
    _calibrar: bool = False
    _ultima_gravacao: float = 0.0
    _cadeado: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def definir_cantos(self, cantos: Cantos) -> None:
        """Confirma os cantos da area de jogo (normalizados), em qualquer ordem de giro.

        A orientacao e conferida no frame seguinte, para que o canto inferior
        esquerdo da imagem retificada seja uma casa escura.
        """
        with self._cadeado:
            self._cantos = cantos
            self._orientados = False
            self._espelhado = False

    def limpar_cantos(self) -> None:
        """Esquece os cantos; a visao volta a sugerir os cantos automaticos."""
        with self._cadeado:
            self._cantos = None
            self._orientados = False
            self._espelhado = False

    def pedir_calibracao(self) -> None:
        """Marca o proximo frame para aprender as cores com a posicao inicial."""
        with self._cadeado:
            self._calibrar = True

    def inverter_lados(self) -> None:
        """Troca o lado da imagem em que ficam as brancas."""
        with self._cadeado:
            self._lado_das_brancas = (
                LadoDasBrancas.CIMA
                if self._lado_das_brancas is LadoDasBrancas.BAIXO
                else LadoDasBrancas.BAIXO
            )

    def processar(self, dados: bytes) -> ResultadoVisao:
        """Processa um frame JPEG e devolve o que foi possivel ler dele."""
        inicio = time.perf_counter()
        imagem = decodificar(dados)
        if imagem is None:
            return ResultadoVisao(Situacao.FRAME_INVALIDO)
        self._gravar(dados)
        with self._cadeado:
            resultado = self._processar(imagem)
        duracao_ms = (time.perf_counter() - inicio) * 1000
        return replace(resultado, duracao_ms=duracao_ms)

    def _processar(self, imagem: Imagem) -> ResultadoVisao:
        """Etapas da visao sobre uma imagem ja decodificada, com o cadeado tomado."""
        altura, largura = imagem.shape[:2]
        if self._cantos is None:
            achados = localizar_tabuleiro(imagem)
            return ResultadoVisao(
                Situacao.SEM_CANTOS,
                largura,
                altura,
                cantos_sugeridos=_normalizar(achados, largura, altura) if achados else None,
            )

        em_pixels = _em_pixels(self._cantos, largura, altura)
        if not self._orientados:
            em_pixels = orientar(imagem, em_pixels)
            self._cantos = _normalizar(em_pixels, largura, altura)
            self._orientados = True

        if self.sensor_de_mao is not None and self.sensor_de_mao.ha_mao_sobre(
            imagem, em_pixels, time.monotonic()
        ):
            return ResultadoVisao(
                Situacao.MAO, largura, altura, cantos=self._cantos, espelhado=self._espelhado
            )

        retificada = retificar(imagem, em_pixels)
        aviso, retificada = self._calibrar_se_pedido(retificada)
        cantos = self._cantos
        previa = codificar_previa(retificada)
        if not self.classificador.calibrado:
            return ResultadoVisao(
                Situacao.SEM_CORES,
                largura,
                altura,
                cantos=cantos,
                espelhado=self._espelhado,
                aviso=aviso,
                previa=previa,
            )

        leituras = self.classificador.classificar(retificada, self._lado_das_brancas)
        minima = obter_config().visao_confianca_min
        return ResultadoVisao(
            Situacao.LEITURA,
            largura,
            altura,
            cantos=cantos,
            lado_das_brancas=self._lado_das_brancas,
            espelhado=self._espelhado,
            leituras=tuple(leituras),
            duvidosas=tuple(i for i, x in enumerate(leituras) if x.confianca < minima),
            aviso=aviso,
            previa=previa,
        )

    def _calibrar_se_pedido(self, retificada: Imagem) -> tuple[str, Imagem]:
        """Calibra as cores se houver pedido pendente.

        Devolve o aviso para o usuario e a imagem retificada que vale dali em diante.
        O lado das brancas e descoberto pela propria imagem: na posicao inicial, e o
        lado com as pecas mais claras.

        Se a posicao inicial nao bate, tenta a imagem transposta. E o caso do tabuleiro
        montado com a casa clara no canto inferior esquerdo de cada jogador: a
        orientacao deixa as pecas nas laterais, e a transposta as leva para cima e
        para baixo sem tirar as casas escuras do lugar. Quando ela serve, os cantos
        passam a ser guardados em ordem invertida, o que transpoe toda retificacao
        seguinte, e a leitura fica espelhada em relacao ao tabuleiro real.
        """
        if not self._calibrar:
            return "", retificada
        self._calibrar = False
        transposta: Imagem = cv2.transpose(retificada).astype(np.uint8)
        erro: CalibracaoInvalida | None = None
        for candidata in (retificada, transposta):
            lado = lado_mais_claro(candidata)
            try:
                self.classificador.calibrar(candidata, lado, ocupacao_inicial())
            except CalibracaoInvalida as falha:
                erro = erro or falha
                continue
            self._lado_das_brancas = lado
            if candidata is retificada:
                return "Cores calibradas.", retificada
            assert self._cantos is not None
            self._cantos = espelhar(self._cantos)
            self._espelhado = not self._espelhado
            return (
                "Cores calibradas. Tabuleiro com casa clara a esquerda de cada jogador: "
                "a leitura e espelhada."
                if self._espelhado
                else "Cores calibradas."
            ), transposta
        return f"Calibracao recusada: {erro}.", retificada

    def _gravar(self, dados: bytes) -> None:
        """Com `gravar_frames` ligado, salva no maximo um frame por segundo em disco."""
        config = obter_config()
        agora = time.monotonic()
        if not config.gravar_frames or agora - self._ultima_gravacao < _INTERVALO_DE_GRAVACAO_S:
            return
        self._ultima_gravacao = agora
        salvar_frame(dados, config.pasta_frames)


def salvar_frame(dados: bytes, pasta: Path) -> Path:
    """Grava um frame JPEG em `pasta`, com o horario no nome, e devolve o caminho."""
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000:06d}.jpg"
    caminho.write_bytes(dados)
    return caminho


def cantos_de(pontos: list[Ponto]) -> Cantos:
    """Converte uma lista de quatro pontos na tupla `Cantos`; ValueError se nao forem quatro."""
    if len(pontos) != 4:
        raise ValueError(f"sao necessarios 4 cantos, vieram {len(pontos)}")
    return (pontos[0], pontos[1], pontos[2], pontos[3])


class TrabalhadorDeVisao:
    """Thread que processa o frame mais recente e entrega o resultado a um ouvinte.

    A fila tem tamanho 1: `enviar` substitui o frame que ainda nao foi processado.
    O ouvinte e chamado na thread do trabalhador.
    """

    def __init__(self, visao: Visao, ao_resultado: Callable[[ResultadoVisao], None]) -> None:
        """Guarda a visao e o ouvinte; a thread so comeca em `iniciar`."""
        self.visao = visao
        self._ao_resultado = ao_resultado
        self._pendente: bytes | None = None
        self._condicao = threading.Condition()
        self._rodando = False
        self._thread: threading.Thread | None = None
        self.descartados: int = 0
        self.processados: int = 0

    def iniciar(self) -> None:
        """Comeca a thread de processamento, se ainda nao estiver rodando."""
        if self._thread is not None:
            return
        self._rodando = True
        self._thread = threading.Thread(target=self._laco, name="visao", daemon=True)
        self._thread.start()

    def enviar(self, dados: bytes) -> None:
        """Entrega um frame; se havia outro esperando, ele e descartado."""
        with self._condicao:
            if self._pendente is not None:
                self.descartados += 1
            self._pendente = dados
            self._condicao.notify()

    def parar(self) -> None:
        """Encerra a thread e espera ela terminar."""
        with self._condicao:
            self._rodando = False
            self._condicao.notify()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _laco(self) -> None:
        """Espera um frame, processa e avisa o ouvinte, ate `parar` ser chamado."""
        while True:
            with self._condicao:
                while self._rodando and self._pendente is None:
                    self._condicao.wait()
                if not self._rodando:
                    return
                dados, self._pendente = self._pendente, None
            assert dados is not None
            resultado = self.visao.processar(dados)
            self.processados += 1
            self._ao_resultado(resultado)
