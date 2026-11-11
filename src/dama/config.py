"""Configuracao do projeto.

Todo valor ajustavel mora aqui e pode ser trocado por variavel de ambiente (prefixo
DAMA_) ou pelo arquivo .env. O codigo le sempre de `obter_config()`.
"""

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Valores ajustaveis do projeto, agrupados por area pelo prefixo do nome.

    Areas: `gambi_` (hub), `llm_` (consulta aos modelos), `minimax_` (busca),
    `avaliacao_` (pesos da avaliacao), `juiz_` (rotulos dos lances), `regras_`,
    `simulacao_` (partidas no terminal), `visao_` e `captura_` (camera).
    Pontuacoes e pesos estao em centesimos de pedra. A descricao de cada campo fica
    na docstring logo abaixo dele.
    """

    model_config = SettingsConfigDict(
        env_prefix="DAMA_",
        env_file=".env",
        extra="ignore",
        frozen=True,
        use_attribute_docstrings=True,
    )

    gambi_hub: str = "http://localhost:3000"
    """Endereco do hub Gambi."""
    gambi_sala: str = ""
    """Codigo da sala Gambi; vazio significa que nenhuma sala foi escolhida."""
    gambi_chave_api: str = "gambi"
    """Chave enviada ao hub. Ele nao autentica; o cliente so exige que nao seja vazia."""
    gambi_modelo_padrao: str = "*"
    """Valor de `model` quando o lado LLM nao escolhe participante ('*' = qualquer um)."""

    porta: PositiveInt = 8443
    """Porta do servidor HTTPS que atende o telefone."""
    endereco: str = "0.0.0.0"
    """Endereco em que o servidor escuta; o padrao aceita conexoes da rede local."""
    pasta_tls: Path = Path("dados/tls")
    """Pasta onde ficam a chave e o certificado autoassinado."""
    tls_validade_dias: PositiveInt = 365
    """Validade, em dias, do certificado gerado."""
    tls_nome: str = "dama-ia-gambi"
    """Nome que aparece no certificado gerado."""
    captura_fps: PositiveInt = 5
    """Quantos frames por segundo o telefone envia."""
    captura_largura: PositiveInt = 1280
    """Largura maxima, em pixels, do frame enviado pelo telefone."""
    captura_qualidade_jpeg: PositiveFloat = 0.7
    """Qualidade JPEG (0 a 1) do frame enviado pelo telefone."""

    llm_timeout_s: PositiveFloat = 60.0
    """Tempo maximo de espera por uma resposta da LLM, em segundos."""
    llm_tentativas: NonNegativeInt = 2
    """Novas tentativas depois de uma resposta invalida ou de um participante ocupado."""
    llm_espera_ocupado_s: NonNegativeFloat = 2.0
    """Espera, em segundos, antes de tentar de novo um participante ocupado."""
    llm_ultimos_lances: NonNegativeInt = 6
    """Quantos lances recentes entram no prompt."""
    llm_lances_de_continuacao: NonNegativeInt = 4
    """Quantos lances da continuacao prevista pelo Minimax entram no prompt."""
    llm_motivo_max: PositiveInt = 300
    """Tamanho maximo, em caracteres, do motivo extraido da resposta."""

    minimax_tempo_s: PositiveFloat = 1.0
    """Tempo que o juiz pode gastar analisando uma posicao, em segundos."""
    minimax_profundidade: PositiveInt = 8
    """Profundidade maxima da busca do juiz, em meios-lances."""
    minimax_pontuacao_vitoria: PositiveInt = 10_000
    """Pontuacao de uma vitoria imediata."""
    minimax_margem_vitoria: PositiveInt = 1_000
    """Pontuacoes a menos desta distancia da vitoria contam como vitoria forcada."""
    minimax_infinito: PositiveInt = 1_000_000
    """Limite da janela alfa-beta; precisa ser maior que qualquer pontuacao."""
    minimax_nos_entre_relogio: PositiveInt = 512
    """De quantos em quantos nos a busca consulta o relogio."""

    avaliacao_valor_pedra: PositiveInt = 100
    """Valor de uma pedra; e a unidade das demais pontuacoes."""
    avaliacao_valor_dama: PositiveInt = 300
    """Valor de uma dama."""
    avaliacao_peso_avanco: NonNegativeInt = 3
    """Bonus por fileira que a pedra ja avancou."""
    avaliacao_peso_centro: NonNegativeInt = 5
    """Bonus por pedra numa casa central."""
    avaliacao_peso_mobilidade: NonNegativeInt = 2
    """Bonus por movimento simples disponivel."""
    avaliacao_peso_ameaca: NonNegativeInt = 15
    """Desconto por peca que o adversario pode capturar com um salto curto."""
    avaliacao_peso_ultima_fileira: NonNegativeInt = 6
    """Bonus por pedra que ainda guarda a propria primeira fileira."""

    juiz_limite_bom: NonNegativeInt = 30
    """Perda maxima para um lance ser rotulado como 'bom'."""
    juiz_limite_duvidoso: NonNegativeInt = 100
    """Perda maxima para um lance ser rotulado como 'duvidoso'; acima disso e 'erro'."""
    juiz_perda_maxima: PositiveInt = 450
    """Teto da perda de um lance na media, para mates nao distorcerem o resumo."""

    regras_limite_lances_de_dama: PositiveInt = 20
    """Empate apos este numero de lances seguidos de dama, sem captura nem lance de pedra."""

    jogo_pausa_entre_lances_s: NonNegativeFloat = 0.6
    """Pausa depois de cada lance de IA no jogo pela tela, para dar tempo de ver o lance."""
    jogo_brancas: str = "humano"
    """Quem joga de brancas no jogo pela tela, antes de o usuario escolher."""
    jogo_pretas: str = "minimax:4"
    """Quem joga de pretas no jogo pela tela, antes de o usuario escolher."""
    jogo_profundidade_facil: PositiveInt = 2
    """Profundidade de busca do adversario 'Minimax facil' do jogo pela tela."""
    jogo_profundidade_media: PositiveInt = 4
    """Profundidade de busca do adversario 'Minimax medio' do jogo pela tela."""
    simulacao_brancas: str = "llm:*"
    """Quem joga de brancas no `dama simular` quando a opcao nao e informada."""
    simulacao_pretas: str = "minimax"
    """Quem joga de pretas no `dama simular` quando a opcao nao e informada."""
    simulacao_max_lances: PositiveInt = 300
    """Numero de lances depois do qual a simulacao e interrompida."""
    simulacao_motivo_max: PositiveInt = 70
    """Quantos caracteres do motivo da LLM aparecem em cada linha da simulacao."""
    pasta_partidas: Path = Path("dados/partidas")
    """Pasta onde as partidas sao gravadas."""
    checagem_amostra_max: PositiveInt = 20
    """Quantos caracteres da resposta de teste o `dama checar-gambi` mostra."""

    visao_largura_max: PositiveInt = 1280
    """Largura maxima, em pixels, do frame processado; frames maiores sao reduzidos."""
    visao_lado_retificado: PositiveInt = 640
    """Lado, em pixels, da vista de topo do tabuleiro."""
    visao_croma_min: PositiveFloat = 8.0
    """Croma (Lab) a partir do qual um pixel conta como parte do tabuleiro colorido."""
    visao_mancha_minima: PositiveFloat = 0.0003
    """Fracao minima da imagem para uma mancha colorida nao ser tratada como ruido."""
    visao_abertura: NonNegativeFloat = 0.002
    """Tamanho da abertura que limpa o ruido da mascara, como fracao da largura da imagem."""
    visao_faixa_do_fundo: PositiveFloat = 0.04
    """Largura da faixa da borda da imagem usada para medir a cor do fundo, como fracao."""
    visao_distancia_do_fundo: PositiveFloat = 14.0
    """Distancia de cor (Lab) ao fundo colorido a partir da qual um pixel e do tabuleiro."""
    visao_peso_da_luz_no_fundo: NonNegativeFloat = 0.5
    """Peso da luminosidade na distancia ao fundo; abaixo de 1, sombras pesam menos."""
    visao_abertura_no_fundo: NonNegativeFloat = 0.01
    """Abertura que apaga a estampa de um fundo colorido, como fracao da largura da imagem."""
    visao_area_minima: PositiveFloat = 0.05
    """Fracao minima da imagem que o tabuleiro precisa ocupar para ser aceito."""
    visao_margem_da_moldura: NonNegativeFloat = 0.02
    """Distancia entre a moldura e a area de jogo, como fracao do lado do tabuleiro."""
    visao_fracao_do_disco: PositiveFloat = 0.6
    """Fracao do lado da casa coberta pela regiao central usada para classifica-la."""
    visao_pixel_estourado: PositiveInt = 250
    """Valor (0-255) a partir do qual um pixel e tratado como reflexo e descartado."""
    visao_fator_de_atualizacao: NonNegativeFloat = 0.05
    """Quanto as cores aprendidas se ajustam a cada lance aceito (0 = nunca mudam)."""
    visao_lado_da_previa: PositiveInt = 320
    """Lado, em pixels, da previa do tabuleiro retificado enviada ao telefone."""
    visao_qualidade_da_previa: PositiveInt = 70
    """Qualidade JPEG (1-100) da previa do tabuleiro retificado."""
    mao_maximo: PositiveInt = 2
    """Quantas maos o detector procura em cada frame."""
    mao_confianca_min: PositiveFloat = 0.5
    """Confianca minima para o detector aceitar uma mao."""
    mao_margem: NonNegativeFloat = 0.1
    """Quanto o tabuleiro e aumentado ao testar se ha uma mao sobre ele."""
    download_timeout_s: PositiveFloat = 120.0
    """Tempo limite, em segundos, para baixar o modelo de mao."""
    pasta_modelos: Path = Path("modelos")
    """Pasta onde fica o modelo de mao baixado."""
    pasta_frames: Path = Path("dados/frames")
    """Pasta onde os frames gravados sao salvos."""
    visao_frames_estaveis: PositiveInt = 5
    """Quantos frames iguais seguidos a visao exige antes de aceitar uma leitura."""
    visao_confianca_min: PositiveFloat = 0.6
    """Confianca minima para aceitar a classificacao de uma casa."""
    captura_timeout_s: PositiveFloat = 15.0
    """Tempo sem receber frames, em segundos, ate a camera ser dada como perdida."""
    gravar_frames: bool = False
    """Grava em disco os frames recebidos, para depuracao."""

    @property
    def minimax_limiar_vitoria(self) -> int:
        """A partir desta pontuacao, a vitoria (ou a derrota) e forcada."""
        return self.minimax_pontuacao_vitoria - self.minimax_margem_vitoria

    @model_validator(mode="after")
    def _conferir_coerencia(self) -> Self:
        """Recusa combinacoes de valores que deixariam o juiz ou a busca sem sentido."""
        if self.juiz_limite_bom > self.juiz_limite_duvidoso:
            raise ValueError("juiz_limite_bom nao pode passar de juiz_limite_duvidoso")
        if self.minimax_margem_vitoria >= self.minimax_pontuacao_vitoria:
            raise ValueError("minimax_margem_vitoria deve ser menor que a pontuacao de vitoria")
        if self.minimax_infinito <= self.minimax_pontuacao_vitoria:
            raise ValueError("minimax_infinito deve ser maior que a pontuacao de vitoria")
        return self


@lru_cache
def obter_config() -> Settings:
    """Devolve a configuracao, lida uma unica vez do ambiente e do arquivo .env."""
    return Settings()
