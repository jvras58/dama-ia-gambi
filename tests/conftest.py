import pytest

from apoio.servidor_falso import ServidorFalso


@pytest.fixture
def servidor() -> ServidorFalso:
    return ServidorFalso()
