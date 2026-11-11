"""Configuracao lida de variaveis de ambiente (prefixo DAMA_) e do arquivo .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DAMA_", env_file=".env", extra="ignore")

    gambi_hub: str = "http://localhost:3000"
    gambi_sala: str = ""
    porta: int = 8443

    llm_timeout_s: float = 60.0
    llm_tentativas: int = 2

    minimax_tempo_s: float = 1.0
    minimax_profundidade: int = 8

    visao_frames_estaveis: int = 5
    visao_confianca_min: float = 0.6
    captura_timeout_s: float = 15.0
    gravar_frames: bool = False


@lru_cache
def obter_config() -> Settings:
    return Settings()
