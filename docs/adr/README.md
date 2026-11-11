# Registros de Decisão de Arquitetura (ADRs)

Cada ADR registra **uma** decisão que seria cara de reverter, com o contexto e as alternativas descartadas. Especificações dizem o que construir; ADRs dizem por que foi construído assim.

## Índice

| ADR | Decisão | Status |
|---|---|---|
| [0001](0001-adotar-sdd-e-estrutura-de-documentos.md) | Adotar SDD e esta estrutura de documentos | Aceito |
| [0002](0002-python-312-com-uv.md) | Python 3.12 gerenciado com uv | Aceito |
| [0003](0003-telefone-como-camera-via-pagina-web.md) | Telefone como câmera via página web; processamento no PC | Aceito |
| [0004](0004-visao-mediapipe-maos-opencv-cor-calibrada.md) | Visão: MediaPipe para mãos, OpenCV e cor calibrada para o tabuleiro | Aceito |
| [0005](0005-damas-rastreadas-pelo-motor-de-regras.md) | Damas promovidas rastreadas pelo motor de regras, não pela câmera | Aceito |
| [0006](0006-regras-damas-brasileiras.md) | Regras de damas brasileiras | Aceito |
| [0007](0007-llm-escolhe-lance-por-indice-via-gambi.md) | LLM via Gambi escolhe o lance por índice numa lista de lances legais | Aceito |
| [0008](0008-papeis-do-minimax.md) | Minimax como juiz, fallback, jogador e analista | Aceito |
| [0009](0009-convencoes-de-codigo.md) | Convenções de código: sem `__init__.py`, valores em `Settings`, tipagem forte, imports completos | Aceito |
| [0010](0010-docstrings-no-lugar-de-comentarios.md) | Docstrings no lugar de comentários | Aceito |

## Como criar um ADR

1. Copie [modelo.md](modelo.md) para `NNNN-titulo-em-kebab-case.md`, com o próximo número.
2. Preencha e adicione a linha no índice acima.
3. Um ADR aceito não é editado para mudar a decisão. Para mudar, crie um novo ADR e marque o antigo como `Substituído por NNNN`.

Status possíveis: `Proposto`, `Aceito`, `Substituído por NNNN`, `Descartado`.
