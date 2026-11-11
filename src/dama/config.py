"""Configuracao do projeto.

Todo valor ajustavel mora aqui e pode ser trocado por variavel de ambiente (prefixo
DAMA_) ou pelo arquivo .env. O codigo le sempre de `obter_config()`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DAMA_", env_file=".env", extra="ignore", frozen=True
    )

    # --- Gambi -----------------------------------------------------------------
    gambi_hub: str = "http://localhost:3000"
    gambi_sala: str = ""
    # O hub nao autentica; o cliente OpenAI so exige que a chave nao seja vazia.
    gambi_chave_api: str = "gambi"
    # Valor de `model` quando o lado LLM nao escolhe participante: "*" = qualquer um.
    gambi_modelo_padrao: str = "*"

    # --- Servidor web ------------------------------------------------------------
    porta: PositiveInt = 8443

    # --- LLM ---------------------------------------------------------------------
    llm_timeout_s: PositiveFloat = 60.0
    # Novas tentativas depois de uma resposta invalida ou de um participante ocupado.
    llm_tentativas: NonNegativeInt = 2
    # Espera antes de tentar de novo quando o participante esta ocupado (409).
    llm_espera_ocupado_s: NonNegativeFloat = 2.0
    # Quantos lances recentes entram no prompt.
    llm_ultimos_lances: NonNegativeInt = 6
    # Quantos lances da continuacao prevista pelo Minimax entram no prompt.
    llm_lances_de_continuacao: NonNegativeInt = 4
    # Tamanho maximo, em caracteres, do motivo extraido da resposta.
    llm_motivo_max: PositiveInt = 300

    # --- Minimax: busca ----------------------------------------------------------
    minimax_tempo_s: PositiveFloat = 1.0
    minimax_profundidade: PositiveInt = 8
    # Pontuacao de uma vitoria imediata, em centesimos de pedra.
    minimax_pontuacao_vitoria: PositiveInt = 10_000
    # Pontuacoes a menos desta distancia da vitoria contam como vitoria forcada.
    minimax_margem_vitoria: PositiveInt = 1_000
    # Limite da janela alfa-beta; precisa ser maior que qualquer pontuacao.
    minimax_infinito: PositiveInt = 1_000_000
    # De quantos em quantos nos a busca consulta o relogio.
    minimax_nos_entre_relogio: PositiveInt = 512

    # --- Minimax: avaliacao (centesimos de pedra) --------------------------------
    avaliacao_valor_pedra: PositiveInt = 100
    avaliacao_valor_dama: PositiveInt = 300
    avaliacao_peso_avanco: NonNegativeInt = 3  # por fileira avancada
    avaliacao_peso_centro: NonNegativeInt = 5  # pedra numa casa central
    avaliacao_peso_mobilidade: NonNegativeInt = 2  # por movimento simples disponivel
    avaliacao_peso_ameaca: NonNegativeInt = 15  # por peca que pode ser capturada num salto
    avaliacao_peso_ultima_fileira: NonNegativeInt = 6  # pedra guardando a primeira fileira

    # --- Juiz: rotulos dos lances (centesimos de pedra) --------------------------
    juiz_limite_bom: NonNegativeInt = 30
    juiz_limite_duvidoso: NonNegativeInt = 100
    # Teto da perda de um lance na media, para mates nao distorcerem o resumo.
    juiz_perda_maxima: PositiveInt = 450

    # --- Regras ------------------------------------------------------------------
    # Empate apos este numero de lances seguidos de dama, sem captura nem lance de pedra.
    regras_limite_lances_de_dama: PositiveInt = 20

    # --- Simulacao no terminal ---------------------------------------------------
    simulacao_brancas: str = "llm:*"
    simulacao_pretas: str = "minimax"
    simulacao_max_lances: PositiveInt = 300
    simulacao_motivo_max: PositiveInt = 70
    pasta_partidas: Path = Path("dados/partidas")
    # Quantos caracteres da resposta de teste o `checar-gambi` mostra.
    checagem_amostra_max: PositiveInt = 20

    # --- Visao e captura ---------------------------------------------------------
    visao_frames_estaveis: PositiveInt = 5
    visao_confianca_min: PositiveFloat = 0.6
    captura_timeout_s: PositiveFloat = 15.0
    gravar_frames: bool = False

    @property
    def minimax_limiar_vitoria(self) -> int:
        """A partir desta pontuacao, a vitoria (ou a derrota) e forcada."""
        return self.minimax_pontuacao_vitoria - self.minimax_margem_vitoria

    @model_validator(mode="after")
    def _conferir_coerencia(self) -> "Settings":
        if self.juiz_limite_bom > self.juiz_limite_duvidoso:
            raise ValueError("juiz_limite_bom nao pode passar de juiz_limite_duvidoso")
        if self.minimax_margem_vitoria >= self.minimax_pontuacao_vitoria:
            raise ValueError("minimax_margem_vitoria deve ser menor que a pontuacao de vitoria")
        if self.minimax_infinito <= self.minimax_pontuacao_vitoria:
            raise ValueError("minimax_infinito deve ser maior que a pontuacao de vitoria")
        return self


@lru_cache
def obter_config() -> Settings:
    return Settings()
