"""Estado de uma partida: lado da vez, historico, fim de jogo e exportacao."""

from dataclasses import dataclass, field
from typing import Final, Self, TypedDict

from dama.config import obter_config
from dama.regras.gerador import aplicar, gerar_lances, promove
from dama.regras.tabuleiro import notacao, para_texto, posicao_inicial
from dama.regras.tipos import (
    BRANCA,
    NOME_COR,
    PRETA,
    VITORIA_DE,
    Cor,
    Lance,
    Peca,
    Resultado,
    Tabuleiro,
    eh_dama,
)

# Marca, na lista de lances em texto, o lance que as brancas nao fizeram.
SEM_LANCE: Final[str] = "..."


class LanceIlegal(ValueError):
    pass


class PartidaDict(TypedDict):
    tabuleiro_inicial: list[Peca]
    vez_inicial: Cor
    lances: list[str]
    empate_por_acordo: bool
    resultado: Resultado | None


@dataclass(frozen=True, slots=True)
class Registro:
    """Um lance jogado, com o necessario para desfaze-lo."""

    lance: Lance
    cor: Cor
    texto: str
    promoveu: bool
    tab_antes: Tabuleiro
    contador_antes: int


@dataclass
class Partida:
    tab: Tabuleiro = field(default_factory=posicao_inicial)
    vez: Cor = BRANCA
    lances_de_dama: int = 0
    historico: list[Registro] = field(default_factory=list)
    empate_por_acordo: bool = False
    _tab_inicial: Tabuleiro = field(init=False, repr=False)
    _vez_inicial: Cor = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._tab_inicial = self.tab
        self._vez_inicial = self.vez

    # --- Lances ------------------------------------------------------------

    def lances_legais(self) -> list[Lance]:
        if self.resultado_por_empate():
            return []
        return gerar_lances(self.tab, self.vez)

    def jogar(self, lance: Lance) -> Registro:
        if lance not in gerar_lances(self.tab, self.vez) or self.resultado_por_empate():
            raise LanceIlegal(f"lance ilegal para as {NOME_COR[self.vez]}: {notacao(lance)}")
        registro = Registro(
            lance=lance,
            cor=self.vez,
            texto=notacao(lance),
            promoveu=promove(self.tab, lance),
            tab_antes=self.tab,
            contador_antes=self.lances_de_dama,
        )
        if eh_dama(self.tab[lance.origem]) and not lance.eh_captura:
            self.lances_de_dama += 1
        else:
            self.lances_de_dama = 0
        self.tab = aplicar(self.tab, lance)
        self.vez = -self.vez
        self.historico.append(registro)
        return registro

    def jogar_texto(self, texto: str) -> Registro:
        """Joga um lance escrito como 'c3-d4' ou 'c3xe5xg7'."""
        return self.jogar(self.lance_de_texto(texto))

    def lance_de_texto(self, texto: str) -> Lance:
        alvo = texto.strip().lower().replace(":", "x")
        for lance in gerar_lances(self.tab, self.vez):
            if notacao(lance) == alvo:
                return lance
        raise LanceIlegal(f"lance ilegal ou mal escrito: {texto!r}")

    def desfazer(self) -> Registro:
        if not self.historico:
            raise LanceIlegal("nao ha lance para desfazer")
        registro = self.historico.pop()
        self.tab = registro.tab_antes
        self.vez = registro.cor
        self.lances_de_dama = registro.contador_antes
        self.empate_por_acordo = False
        return registro

    # --- Fim de jogo -------------------------------------------------------

    def resultado_por_empate(self) -> bool:
        limite = obter_config().regras_limite_lances_de_dama
        return self.empate_por_acordo or self.lances_de_dama >= limite

    def resultado(self) -> Resultado | None:
        """Quem venceu, empate, ou None se o jogo continua."""
        if self.resultado_por_empate():
            return Resultado.EMPATE
        if not gerar_lances(self.tab, self.vez):
            # Sem pecas ou sem lances: o lado da vez perde.
            return VITORIA_DE[-self.vez]
        return None

    def encerrada(self) -> bool:
        return self.resultado() is not None

    # --- Exportacao --------------------------------------------------------

    def para_dict(self) -> PartidaDict:
        return {
            "tabuleiro_inicial": list(self._tab_inicial),
            "vez_inicial": self._vez_inicial,
            "lances": [r.texto for r in self.historico],
            "empate_por_acordo": self.empate_por_acordo,
            "resultado": self.resultado(),
        }

    @classmethod
    def de_dict(cls, dados: PartidaDict) -> Self:
        partida = cls(tab=tuple(dados["tabuleiro_inicial"]), vez=dados["vez_inicial"])
        for texto in dados["lances"]:
            partida.jogar_texto(texto)
        partida.empate_por_acordo = bool(dados.get("empate_por_acordo", False))
        return partida

    def para_texto(self) -> str:
        """Lances numerados, um par (brancas, pretas) por linha, seguidos do tabuleiro atual."""
        linhas: list[str] = []
        textos = [r.texto for r in self.historico]
        if self._vez_inicial == PRETA:
            textos.insert(0, SEM_LANCE)
        for n in range(0, len(textos), 2):
            par = " ".join(textos[n : n + 2])
            linhas.append(f"{n // 2 + 1}. {par}")
        resultado = self.resultado()
        if resultado:
            linhas.append(f"Resultado: {resultado}")
        linhas.append("")
        linhas.append(para_texto(self.tab))
        return "\n".join(linhas)
