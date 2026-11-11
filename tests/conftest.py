import sys
from pathlib import Path

import pytest

# Permite `from servidor_falso import ...` em qualquer pasta de testes.
sys.path.insert(0, str(Path(__file__).parent / "llm"))

from servidor_falso import ServidorFalso  # noqa: E402


@pytest.fixture
def servidor() -> ServidorFalso:
    return ServidorFalso()
