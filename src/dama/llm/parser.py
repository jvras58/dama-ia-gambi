"""Leitura da resposta da LLM, em texto livre.

Ordem de tentativa:
1. 'LANCE: n' (o formato pedido);
2. um lance em notacao ('c3-d4', 'c3xe5') que esteja na lista de legais;
3. um unico numero valido solto no texto.
Qualquer ambiguidade e tratada como resposta invalida.
"""

import re

_PENSAMENTO = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
_LANCE = re.compile(r"\blance\b\W{0,5}(\d{1,3})\b", re.IGNORECASE)
_NOTACAO = re.compile(r"\b[a-h][1-8](?:\s*[-x:]\s*[a-h][1-8])+\b", re.IGNORECASE)
_NUMERO = re.compile(r"(?<![\w.,])\d{1,3}(?![\w]|[.,]\d)")
_MOTIVO = re.compile(r"\bmotivo\b\s*[:=-]?\s*(.+)", re.IGNORECASE)


def _limpar(texto: str) -> str:
    return _PENSAMENTO.sub(" ", texto)


def extrair_lance(texto: str, legais: list[str]) -> int | None:
    """Indice (base 0) do lance escolhido em `legais`, ou None se a resposta nao serve."""
    texto = _limpar(texto)
    n = len(legais)

    marcados = {int(m) for m in _LANCE.findall(texto)}
    if marcados:
        validos = {m for m in marcados if 1 <= m <= n}
        return validos.pop() - 1 if len(validos) == 1 and len(marcados) == 1 else None

    citados = set()
    for trecho in _NOTACAO.findall(texto):
        normal = re.sub(r"\s+", "", trecho.lower()).replace(":", "x")
        for i, legal in enumerate(legais):
            # Aceita 'c3-e5' para a captura 'c3xe5': o separador nao importa.
            if re.split(r"[-x]", normal) == re.split(r"[-x]", legal):
                citados.add(i)
    if citados:
        return citados.pop() if len(citados) == 1 else None

    numeros = {int(m) for m in _NUMERO.findall(texto)}
    validos = {m for m in numeros if 1 <= m <= n}
    if len(validos) == 1 and len(numeros) == 1:
        return validos.pop() - 1
    return None


def extrair_motivo(texto: str) -> str:
    achado = _MOTIVO.search(_limpar(texto))
    if not achado:
        return ""
    return achado.group(1).strip().splitlines()[0][:300]
