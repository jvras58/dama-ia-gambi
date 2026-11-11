"""Testes das convencoes de codigo do projeto (ADRs 0009 e 0010)."""

import ast
import io
import tokenize
from pathlib import Path

import pytest

RAIZ = Path(__file__).parent.parent
ARQUIVOS = sorted([*RAIZ.glob("src/**/*.py"), *RAIZ.glob("tests/**/*.py")])
DIRETIVAS = ("fmt:", "noqa", "type:")


def _nome(caminho: Path) -> str:
    """Caminho relativo a raiz do projeto, para identificar o caso de teste."""
    return caminho.relative_to(RAIZ).as_posix()


def _sem_docstring(no: ast.AST, prefixo: str = "") -> list[str]:
    """Nomes das funcoes e classes dentro de `no` que nao tem docstring."""
    faltam: list[str] = []
    for filho in ast.iter_child_nodes(no):
        if isinstance(filho, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            nome = f"{prefixo}{filho.name}"
            if ast.get_docstring(filho) is None:
                faltam.append(nome)
            faltam.extend(_sem_docstring(filho, f"{nome}."))
        else:
            faltam.extend(_sem_docstring(filho, prefixo))
    return faltam


@pytest.mark.parametrize("caminho", ARQUIVOS, ids=_nome)
def test_modulos_funcoes_e_classes_tem_docstring(caminho: Path) -> None:
    """Todo modulo, funcao (publica, privada ou aninhada) e classe tem docstring."""
    arvore = ast.parse(caminho.read_text("utf-8"))
    assert ast.get_docstring(arvore) is not None, "modulo sem docstring"
    assert _sem_docstring(arvore) == []


@pytest.mark.parametrize("caminho", ARQUIVOS, ids=_nome)
def test_nao_ha_comentarios_soltos(caminho: Path) -> None:
    """O que precisa ser explicado vai em docstring; so diretivas de ferramenta ficam."""
    fonte = io.StringIO(caminho.read_text("utf-8"))
    comentarios = [
        f"linha {token.start[0]}: {token.string}"
        for token in tokenize.generate_tokens(fonte.readline)
        if token.type == tokenize.COMMENT and not any(d in token.string for d in DIRETIVAS)
    ]
    assert comentarios == []


@pytest.mark.parametrize("caminho", ARQUIVOS, ids=_nome)
def test_nao_ha_arquivos_init(caminho: Path) -> None:
    """O projeto usa pacotes de namespace: nenhum `__init__.py`."""
    assert caminho.name != "__init__.py"
