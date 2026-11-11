"""Subida do servidor HTTPS que atende o telefone.

Junta o certificado, a visao (com o detector de mao, se o modelo estiver baixado) e a
aplicacao web, e roda tudo no uvicorn. Tambem monta o QR code com o endereco, para
abrir a pagina no telefone sem digitar.
"""

import io
from dataclasses import dataclass
from pathlib import Path

import qrcode
import uvicorn

from dama.config import Settings
from dama.visao.pipeline import SensorDeMao, Visao
from dama.web.app import criar_app
from dama.web.sessao import Sessao
from dama.web.tls import enderecos_locais, garantir_certificado


@dataclass(frozen=True, slots=True)
class Acesso:
    """Como chegar ao servidor a partir de outro aparelho da rede."""

    enderecos: list[str]
    """Enderecos HTTPS, com o da rede local primeiro."""
    certificado: Path
    chave: Path

    @property
    def principal(self) -> str:
        """O endereco que o telefone deve abrir."""
        return self.enderecos[0]


def preparar_acesso(config: Settings) -> Acesso:
    """Garante o certificado e monta os enderecos em que a pagina fica disponivel."""
    ips = enderecos_locais()
    certificado, chave = garantir_certificado(config.pasta_tls, ips)
    return Acesso([f"https://{ip}:{config.porta}" for ip in ips], certificado, chave)


def qr_em_texto(endereco: str) -> str:
    """QR code do endereco, desenhado com caracteres para o terminal."""
    codigo = qrcode.QRCode(border=2)
    codigo.add_data(endereco)
    codigo.make(fit=True)
    saida = io.StringIO()
    codigo.print_ascii(out=saida, invert=True)
    return saida.getvalue()


def criar_sensor_de_mao() -> SensorDeMao | None:
    """Detector de mao, ou None se o modelo ainda nao foi baixado.

    O modulo do detector so e importado aqui, porque carregar o MediaPipe leva alguns
    segundos e os outros comandos (`simular`, `checar-gambi`) nao precisam dele.
    """
    from dama.visao.mao import DetectorDeMao, modelo_disponivel

    return DetectorDeMao() if modelo_disponivel() else None


def servir(config: Settings, acesso: Acesso, sensor_de_mao: SensorDeMao | None) -> None:
    """Roda o servidor ate ser interrompido (Ctrl+C)."""
    sessao = Sessao(Visao(sensor_de_mao=sensor_de_mao))
    uvicorn.run(
        criar_app(sessao),
        host=config.endereco,
        port=config.porta,
        ssl_certfile=str(acesso.certificado),
        ssl_keyfile=str(acesso.chave),
        log_level="warning",
    )
