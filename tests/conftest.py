"""Fixtures compartilhadas pelos testes."""

import pytest

from apoio.servidor_falso import ServidorFalso


@pytest.fixture
def servidor() -> ServidorFalso:
    """Um servidor Gambi falso novo para cada teste."""
    return ServidorFalso()
