"""Certificado autoassinado para servir a pagina em HTTPS na rede local.

Navegadores de telefone so liberam a camera em contexto seguro, entao a pagina precisa
de HTTPS mesmo dentro de casa. O certificado e gerado na primeira execucao, guardado em
`pasta_tls` e refeito quando os enderecos da maquina mudam ou a validade acaba. Como ele
nao e assinado por uma autoridade conhecida, o navegador mostra um aviso na primeira
visita, que o usuario precisa aceitar.
"""

import ipaddress
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from dama.config import obter_config

ARQUIVO_DO_CERTIFICADO: Final[str] = "certificado.pem"
ARQUIVO_DA_CHAVE: Final[str] = "chave.pem"
_LOCAL: Final[str] = "127.0.0.1"
_NOME_LOCAL: Final[str] = "localhost"
_DESTINO_DE_SONDAGEM: Final[tuple[str, int]] = ("10.255.255.255", 1)
_FOLGA_DO_RELOGIO: Final[timedelta] = timedelta(minutes=5)


def enderecos_locais() -> list[str]:
    """Enderecos IPv4 desta maquina, com o da rede local primeiro e 127.0.0.1 por ultimo.

    O endereco principal e descoberto abrindo um soquete UDP para um endereco privado:
    nada e enviado, mas o sistema escolhe a interface que usaria para a rede local.
    """
    achados: list[str] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sonda:
        try:
            sonda.connect(_DESTINO_DE_SONDAGEM)
            achados.append(str(sonda.getsockname()[0]))
        except OSError:
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            achados.append(str(info[4][0]))
    except OSError:
        pass
    unicos = [ip for ip in dict.fromkeys(achados) if ip != _LOCAL]
    return [*unicos, _LOCAL]


def _ips_do_certificado(certificado: x509.Certificate) -> set[str]:
    """Enderecos IP listados no certificado."""
    try:
        nomes = certificado.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return set()
    return {str(ip) for ip in nomes.value.get_values_for_type(x509.IPAddress)}


def _serve(caminho: Path, enderecos: list[str]) -> bool:
    """Diz se o certificado em disco ainda vale e cobre todos os enderecos atuais."""
    try:
        certificado = x509.load_pem_x509_certificate(caminho.read_bytes())
    except (OSError, ValueError):
        return False
    agora = datetime.now(UTC)
    no_prazo = certificado.not_valid_before_utc <= agora <= certificado.not_valid_after_utc
    return no_prazo and set(enderecos) <= _ips_do_certificado(certificado)


def gerar_certificado(enderecos: list[str]) -> tuple[bytes, bytes]:
    """Gera a chave e o certificado autoassinado, em PEM, para os enderecos dados."""
    config = obter_config()
    chave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, config.tls_nome)])
    alternativos = [
        x509.DNSName(_NOME_LOCAL),
        *(x509.IPAddress(ipaddress.ip_address(ip)) for ip in enderecos),
    ]
    agora = datetime.now(UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - _FOLGA_DO_RELOGIO)
        .not_valid_after(agora + timedelta(days=config.tls_validade_dias))
        .add_extension(x509.SubjectAlternativeName(alternativos), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(chave, hashes.SHA256())
    )
    chave_pem = chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return chave_pem, certificado.public_bytes(serialization.Encoding.PEM)


def garantir_certificado(pasta: Path, enderecos: list[str]) -> tuple[Path, Path]:
    """Devolve os caminhos do certificado e da chave, gerando-os se for preciso."""
    caminho_do_certificado = pasta / ARQUIVO_DO_CERTIFICADO
    caminho_da_chave = pasta / ARQUIVO_DA_CHAVE
    if caminho_da_chave.is_file() and _serve(caminho_do_certificado, enderecos):
        return caminho_do_certificado, caminho_da_chave
    pasta.mkdir(parents=True, exist_ok=True)
    chave_pem, certificado_pem = gerar_certificado(enderecos)
    caminho_da_chave.write_bytes(chave_pem)
    caminho_do_certificado.write_bytes(certificado_pem)
    return caminho_do_certificado, caminho_da_chave
