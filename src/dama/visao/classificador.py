"""Classificacao das 32 casas escuras em vazia, peca branca ou peca preta.

O classificador de cor aprende a aparencia das tres classes na calibracao, feita com a
posicao inicial montada: ali se sabe que 12 casas tem peca branca, 12 tem peca preta e
8 estao vazias. Cada casa e resumida por duas caracteristicas da sua regiao central:

- luminosidade (L do espaco Lab), que separa peca branca de peca preta;
- croma, que separa casa vazia (marrom, colorida) de peca (branca ou preta, sem cor).

Usa-se a mediana, e os pixels estourados (reflexos) sao descartados, porque o tabuleiro
e brilhante e um reflexo numa casa vazia imitaria uma peca branca.
"""

from collections.abc import Sequence
from typing import Final, Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from dama.config import obter_config
from dama.regras.tabuleiro import N_CASAS, PEDRAS_POR_LADO, posicao_inicial
from dama.regras.tipos import PEDRA, Tabuleiro
from dama.visao.localizacao import croma, posicao_na_imagem, recorte_da_casa
from dama.visao.tipos import Imagem, LadoDasBrancas, LeituraCasa, Ocupacao

type Caracteristicas = NDArray[np.float64]

CLASSES: Final[tuple[Ocupacao, ...]] = tuple(Ocupacao)
_N_CARACTERISTICAS: Final[int] = 2
_FRACAO_MINIMA_VALIDA: Final[float] = 0.5
_EPSILON: Final[float] = 1e-6


class CalibracaoInvalida(ValueError):
    """A imagem usada na calibracao nao parece a posicao inicial."""


def ocupacao_esperada(tab: Tabuleiro) -> list[Ocupacao]:
    """O que a camera deve ver em cada casa de `tab` (damas contam como pedras)."""
    return [
        Ocupacao.VAZIA if peca == 0 else Ocupacao.BRANCA if peca > 0 else Ocupacao.PRETA
        for peca in tab
    ]


def extrair(retificada: Imagem, lado_das_brancas: LadoDasBrancas) -> Caracteristicas:
    """Luminosidade e croma medianos da regiao central de cada casa escura.

    Devolve uma matriz 32x2, na ordem dos indices das casas. Pixels estourados sao
    descartados como reflexo, a menos que sejam mais da metade da regiao: ai a casa
    inteira e clara (uma peca branca sob luz forte) e todos os pixels contam.
    """
    config = obter_config()
    luminosidade = cv2.cvtColor(retificada, cv2.COLOR_BGR2LAB)[:, :, 0].astype(np.float64)
    mapa_de_croma = croma(retificada).astype(np.float64)
    maximo = retificada.max(axis=2)
    saida = np.zeros((N_CASAS, _N_CARACTERISTICAS), dtype=np.float64)
    for casa in range(N_CASAS):
        linha, coluna = posicao_na_imagem(casa, lado_das_brancas)
        fracao = config.visao_fracao_do_disco
        claro = recorte_da_casa(luminosidade, linha, coluna, fracao)
        colorido = recorte_da_casa(mapa_de_croma, linha, coluna, fracao)
        validos = recorte_da_casa(maximo, linha, coluna, fracao) < config.visao_pixel_estourado
        if float(validos.mean()) < _FRACAO_MINIMA_VALIDA:
            validos = np.ones_like(validos, dtype=bool)
        saida[casa] = (float(np.median(claro[validos])), float(np.median(colorido[validos])))
    return saida


def lado_mais_claro(retificada: Imagem) -> LadoDasBrancas:
    """Na posicao inicial, diz de que lado da imagem estao as pecas brancas.

    Compara a luminosidade das 12 casas mais proximas de cada borda.
    """
    caracteristicas = extrair(retificada, LadoDasBrancas.BAIXO)
    de_baixo = float(np.median(caracteristicas[:PEDRAS_POR_LADO, 0]))
    de_cima = float(np.median(caracteristicas[-PEDRAS_POR_LADO:, 0]))
    return LadoDasBrancas.BAIXO if de_baixo >= de_cima else LadoDasBrancas.CIMA


class Classificador(Protocol):
    """O que o pipeline de visao espera de um classificador de casas."""

    @property
    def calibrado(self) -> bool:
        """Diz se o classificador ja aprendeu as cores e pode classificar."""
        ...

    def calibrar(
        self,
        retificada: Imagem,
        lado_das_brancas: LadoDasBrancas,
        esperado: Sequence[Ocupacao],
    ) -> None:
        """Aprende a aparencia de cada classe a partir de uma posicao conhecida."""
        ...

    def classificar(
        self, retificada: Imagem, lado_das_brancas: LadoDasBrancas
    ) -> list[LeituraCasa]:
        """Classifica as 32 casas escuras, na ordem dos indices das casas."""
        ...

    def atualizar(
        self,
        retificada: Imagem,
        lado_das_brancas: LadoDasBrancas,
        esperado: Sequence[Ocupacao],
    ) -> None:
        """Ajusta levemente o que foi aprendido, depois de um lance aceito."""
        ...


class ClassificadorCor:
    """Classificador por centroide mais proximo em luminosidade e croma.

    `centroides` tem uma linha por classe (na ordem de `CLASSES`) e `escala` e o
    desvio de cada caracteristica na calibracao, usado para que luminosidade e croma
    pesem o mesmo na distancia.
    """

    def __init__(self) -> None:
        """Comeca sem calibracao."""
        self.centroides: Caracteristicas | None = None
        self.escala: Caracteristicas = np.ones(_N_CARACTERISTICAS, dtype=np.float64)

    @property
    def calibrado(self) -> bool:
        """Diz se o classificador ja aprendeu as cores e pode classificar."""
        return self.centroides is not None

    def calibrar(
        self,
        retificada: Imagem,
        lado_das_brancas: LadoDasBrancas,
        esperado: Sequence[Ocupacao],
    ) -> None:
        """Aprende o centroide de cada classe a partir de uma posicao conhecida.

        Levanta `CalibracaoInvalida` se alguma classe nao aparece em `esperado`, ou
        se as classes aprendidas nao ficam separadas o bastante para reclassificar
        corretamente, com confianca, as proprias casas da calibracao. E o que
        acontece quando o tabuleiro esta vazio ou fora da posicao inicial.
        """
        config = obter_config()
        caracteristicas = extrair(retificada, lado_das_brancas)
        escala = np.maximum(caracteristicas.std(axis=0), _EPSILON)
        centroides = np.zeros((len(CLASSES), _N_CARACTERISTICAS), dtype=np.float64)
        for indice, classe in enumerate(CLASSES):
            da_classe = [i for i, ocupacao in enumerate(esperado) if ocupacao is classe]
            if not da_classe:
                raise CalibracaoInvalida(f"a posicao de calibracao nao tem casa '{classe}'")
            centroides[indice] = np.median(caracteristicas[da_classe], axis=0)

        leituras = _classificar(caracteristicas, centroides, escala)
        erradas = [
            i
            for i, leitura in enumerate(leituras)
            if leitura.ocupacao is not esperado[i] or leitura.confianca < config.visao_confianca_min
        ]
        if erradas:
            raise CalibracaoInvalida(
                f"{len(erradas)} casa(s) nao batem com a posicao inicial; "
                "confira as pecas, os cantos e a iluminacao"
            )
        self.centroides = centroides
        self.escala = escala

    def classificar(
        self, retificada: Imagem, lado_das_brancas: LadoDasBrancas
    ) -> list[LeituraCasa]:
        """Classifica as 32 casas escuras, na ordem dos indices das casas."""
        if self.centroides is None:
            raise CalibracaoInvalida("o classificador ainda nao foi calibrado")
        caracteristicas = extrair(retificada, lado_das_brancas)
        return _classificar(caracteristicas, self.centroides, self.escala)

    def atualizar(
        self,
        retificada: Imagem,
        lado_das_brancas: LadoDasBrancas,
        esperado: Sequence[Ocupacao],
    ) -> None:
        """Move cada centroide um pouco na direcao do que a camera ve agora.

        `esperado` e a ocupacao conhecida depois de um lance aceito. O passo e
        `visao_fator_de_atualizacao`; serve para acompanhar a mudanca lenta da luz.
        """
        if self.centroides is None:
            return
        fator = obter_config().visao_fator_de_atualizacao
        caracteristicas = extrair(retificada, lado_das_brancas)
        for indice, classe in enumerate(CLASSES):
            da_classe = [i for i, ocupacao in enumerate(esperado) if ocupacao is classe]
            if da_classe:
                observado = np.median(caracteristicas[da_classe], axis=0)
                self.centroides[indice] += fator * (observado - self.centroides[indice])


def _classificar(
    caracteristicas: Caracteristicas, centroides: Caracteristicas, escala: Caracteristicas
) -> list[LeituraCasa]:
    """Classe do centroide mais proximo de cada casa e a confianca da escolha.

    A confianca e 1 - d1/d2, em que d1 e a distancia ao centroide mais proximo e d2 ao
    segundo: 1 quando a casa esta em cima de um centroide, 0 quando esta no meio de dois.
    """
    leituras: list[LeituraCasa] = []
    for linha in caracteristicas:
        distancias = np.linalg.norm((centroides - linha) / escala, axis=1)
        ordem = np.argsort(distancias)
        primeira, segunda = float(distancias[ordem[0]]), float(distancias[ordem[1]])
        confianca = 1.0 - primeira / max(segunda, _EPSILON)
        leituras.append(LeituraCasa(CLASSES[int(ordem[0])], max(0.0, min(1.0, confianca))))
    return leituras


def ocupacao_inicial() -> list[Ocupacao]:
    """Ocupacao esperada na posicao inicial: 12 brancas, 8 vazias, 12 pretas."""
    tab = posicao_inicial()
    assert tab.count(PEDRA) == PEDRAS_POR_LADO
    return ocupacao_esperada(tab)
