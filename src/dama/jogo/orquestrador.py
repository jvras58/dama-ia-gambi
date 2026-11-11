"""Maquina de estados da partida.

A cada turno:
1. o juiz (Minimax) analisa a posicao;
2. o controlador do lado da vez escolhe um lance, ou o lance vem de fora (humano/camera);
3. o lance e aplicado, rotulado pelo juiz e registrado.

No modo simulado, o lance de uma IA e aplicado na hora. Fora dele, fica pendente ate que
`confirmar_execucao` informe que o tabuleiro fisico reflete o lance.
"""

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from dataclasses import dataclass, field

from ..llm.jogador import Decisao
from ..minimax.analise import AnalisePosicao, ResumoLado, analisar, resumir
from ..regras.partida import LanceIlegal, Partida
from ..regras.tabuleiro import notacao
from ..regras.tipos import BRANCA, NOME_COR, PRETA, Lance
from .controladores import TIPO_HUMANO, Controlador

PREPARANDO = "preparando"
EM_JOGO = "em_jogo"
AGUARDANDO_EXECUCAO = "aguardando_execucao"
PAUSADA = "pausada"
ENCERRADA = "encerrada"

ORIGEM_HUMANO = "humano"

MODO_IA_X_IA = "ia_x_ia"
MODO_ASSISTIDO = "assistido"

Analisador = Callable[[Partida], Awaitable[AnalisePosicao]]
Ouvinte = Callable[[str, dict], None]


def criar_analisador(
    profundidade: int = 8, tempo_s: float | None = 1.0, executor: Executor | None = None
) -> Analisador:
    """Analisador que roda o Minimax fora do laco de eventos.

    Com `executor=None` usa a thread padrao do asyncio; o servidor web passa um
    ProcessPoolExecutor para nao disputar a CPU com a visao.
    """

    async def analisador(partida: Partida) -> AnalisePosicao:
        laco = asyncio.get_running_loop()
        return await laco.run_in_executor(
            executor, analisar, partida.tab, partida.vez, profundidade, tempo_s
        )

    return analisador


@dataclass
class LanceJogado:
    numero: int
    cor: int
    texto: str
    origem: str  # llm | fallback | unico | minimax | humano
    motivo: str
    rotulo: str
    pontuacao: int
    perda: int
    registro_llm: dict | None = None

    def para_dict(self) -> dict:
        return {
            "numero": self.numero,
            "cor": NOME_COR[self.cor],
            "lance": self.texto,
            "origem": self.origem,
            "motivo": self.motivo,
            "rotulo": self.rotulo,
            "pontuacao": self.pontuacao,
            "perda": self.perda,
            "registro_llm": self.registro_llm,
        }

    @classmethod
    def de_dict(cls, dados: dict) -> "LanceJogado":
        return cls(
            numero=dados["numero"],
            cor=BRANCA if dados["cor"] == NOME_COR[BRANCA] else PRETA,
            texto=dados["lance"],
            origem=dados["origem"],
            motivo=dados["motivo"],
            rotulo=dados["rotulo"],
            pontuacao=dados["pontuacao"],
            perda=dados["perda"],
            registro_llm=dados.get("registro_llm"),
        )


@dataclass
class Orquestrador:
    partida: Partida
    controladores: dict[int, Controlador]
    analisador: Analisador
    modo: str = MODO_IA_X_IA
    simulado: bool = True
    conselheiro: Controlador | None = None  # modo assistido: sugere lances
    cor_assistida: int | None = None
    ouvinte: Ouvinte | None = None
    lances: list[LanceJogado] = field(default_factory=list)
    estado: str = PREPARANDO
    pendente: Decisao | None = None
    _analise: AnalisePosicao | None = field(default=None, repr=False)
    _estado_antes_da_pausa: str = field(default=EM_JOGO, repr=False)

    # --- Controle ------------------------------------------------------------

    def iniciar(self) -> None:
        if self.estado == PREPARANDO:
            self._mudar_estado(ENCERRADA if self.partida.encerrada() else EM_JOGO)

    def pausar(self) -> None:
        if self.estado in (EM_JOGO, AGUARDANDO_EXECUCAO):
            self._estado_antes_da_pausa = self.estado
            self._mudar_estado(PAUSADA)

    def retomar(self) -> None:
        if self.estado == PAUSADA:
            self._mudar_estado(self._estado_antes_da_pausa)

    def encerrar(self, empate: bool = False) -> None:
        if empate:
            self.partida.empate_por_acordo = True
        self.pendente = None
        self._mudar_estado(ENCERRADA)

    # --- Turno ---------------------------------------------------------------

    async def analise_atual(self) -> AnalisePosicao:
        """Analise do juiz para a posicao da vez (calculada uma vez por posicao)."""
        if self._analise is None:
            self._analise = await self.analisador(self.partida)
        return self._analise

    async def passo(self) -> LanceJogado | None:
        """Avanca um turno de IA. Devolve o lance aplicado, ou None se nada foi aplicado.

        Nao faz nada se a partida nao esta em jogo ou se o lado da vez e humano.
        """
        if self.estado != EM_JOGO:
            return None
        controlador = self.controladores[self.partida.vez]
        analise = await self.analise_atual()
        decisao = await controlador.escolher(self.partida, analise)
        if decisao is None or self.estado != EM_JOGO:
            return None
        if self.simulado:
            return self._aplicar(decisao.lance, decisao)
        self.pendente = decisao
        self._mudar_estado(AGUARDANDO_EXECUCAO)
        self._emitir(
            "lance_pendente",
            {
                "cor": NOME_COR[self.partida.vez],
                "lance": notacao(decisao.lance),
                "origem": decisao.origem,
                "motivo": decisao.motivo,
            },
        )
        return None

    async def confirmar_execucao(self, lance: Lance) -> LanceJogado:
        """O tabuleiro fisico mostra `lance`; so vale se for o lance pendente."""
        if self.estado != AGUARDANDO_EXECUCAO or self.pendente is None:
            raise LanceIlegal("nao ha lance pendente de execucao")
        if lance != self.pendente.lance:
            raise LanceIlegal(
                f"esperado {notacao(self.pendente.lance)}, executado {notacao(lance)}"
            )
        decisao, self.pendente = self.pendente, None
        self.estado = EM_JOGO
        await self.analise_atual()
        return self._aplicar(lance, decisao)

    async def lance_humano(self, lance: Lance) -> LanceJogado:
        """Lance vindo de fora (camera ou interface) para um lado humano."""
        if self.estado != EM_JOGO:
            raise LanceIlegal(f"a partida nao esta em jogo ({self.estado})")
        if self.controladores[self.partida.vez].tipo != TIPO_HUMANO:
            raise LanceIlegal(f"o lado das {NOME_COR[self.partida.vez]} nao e humano")
        if lance not in self.partida.lances_legais():
            raise LanceIlegal(f"lance ilegal: {notacao(lance)}")
        await self.analise_atual()
        return self._aplicar(lance, None)

    async def sugerir(self) -> Decisao | None:
        """Sugestao do conselheiro para o jogador assistido, se for a vez dele."""
        if (
            self.conselheiro is None
            or self.estado != EM_JOGO
            or self.partida.vez != self.cor_assistida
        ):
            return None
        analise = await self.analise_atual()
        decisao = await self.conselheiro.escolher(self.partida, analise)
        if decisao is not None:
            item = analise.de(decisao.lance)
            self._emitir(
                "sugestao",
                {
                    "lance": notacao(decisao.lance),
                    "origem": decisao.origem,
                    "motivo": decisao.motivo,
                    "minimax": item.descricao() if item else "",
                },
            )
        return decisao

    async def rodar(self, max_lances: int | None = None) -> None:
        """Joga ate o fim (ou ate `max_lances`), enquanto os lados forem IAs simuladas."""
        self.iniciar()
        jogados = 0
        while self.estado == EM_JOGO and (max_lances is None or jogados < max_lances):
            if await self.passo() is None:
                break
            jogados += 1

    def desfazer(self) -> None:
        self.partida.desfazer()
        if self.lances:
            self.lances.pop()
        self.pendente = None
        self._analise = None
        self._mudar_estado(EM_JOGO)

    # --- Consulta ------------------------------------------------------------

    def resumo_do_juiz(self) -> dict[str, ResumoLado]:
        return resumir([(x.cor, x.rotulo, x.perda) for x in self.lances if x.rotulo])

    def taxa_de_fallback(self) -> dict[str, float]:
        taxas = {}
        for cor in (BRANCA, PRETA):
            consultas = [x for x in self.lances if x.cor == cor and x.origem in ("llm", "fallback")]
            falhas = sum(1 for x in consultas if x.origem == "fallback")
            taxas[NOME_COR[cor]] = falhas / len(consultas) if consultas else 0.0
        return taxas

    # --- Interno -------------------------------------------------------------

    def _aplicar(self, lance: Lance, decisao: Decisao | None) -> LanceJogado:
        analise = self._analise
        item = analise.de(lance) if analise else None
        cor = self.partida.vez
        registro = self.partida.jogar(lance)
        jogado = LanceJogado(
            numero=len(self.partida.historico),
            cor=cor,
            texto=registro.texto,
            origem=decisao.origem if decisao else ORIGEM_HUMANO,
            motivo=decisao.motivo if decisao else "",
            rotulo=item.rotulo if item else "",
            pontuacao=item.pontuacao if item else 0,
            perda=item.perda if item else 0,
            registro_llm=decisao.registro.para_dict() if decisao and decisao.registro else None,
        )
        self.lances.append(jogado)
        self._analise = None
        self._emitir("lance", jogado.para_dict())
        if self.partida.encerrada():
            self._mudar_estado(ENCERRADA)
        return jogado

    def _mudar_estado(self, novo: str) -> None:
        if novo != self.estado:
            self.estado = novo
            self._emitir("estado", {"estado": novo, "resultado": self.partida.resultado()})

    def _emitir(self, tipo: str, dados: dict) -> None:
        if self.ouvinte is not None:
            self.ouvinte(tipo, dados)
