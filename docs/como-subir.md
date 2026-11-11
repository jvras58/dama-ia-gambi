# Como subir tudo

Passo a passo para jogar pela tela do telefone ou do PC, com ou sem LLM. Os comandos são para o PowerShell do Windows, na pasta do projeto.

## O que precisa estar instalado

| Programa | Para quê | Como conferir |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Rodar o projeto (Python 3.12 vem junto). | `uv --version` |
| [Gambi](https://www.gambi.sh/pt-br/) 0.7.2 ou mais novo | Servir as LLMs. Só para jogar contra uma LLM. | `gambi --version` |
| [Ollama](https://ollama.com/) com um modelo baixado | Rodar o modelo no PC. Só para jogar contra uma LLM. | `ollama list` |

Na primeira vez, instale as dependências do projeto:

```bash
uv sync
```

## Só o jogo, sem LLM

Um terminal basta:

```bash
uv run dama serve
```

O terminal mostra o endereço `https://<ip>:8443` e um QR code. Abra no telefone (na mesma rede Wi-Fi) ou no navegador do PC. O certificado é autoassinado: o navegador avisa que a conexão não é segura; escolha "Avançado" e siga para o site.

Na página, escolha quem joga de cada lado e toque em "Nova partida". Sem o Gambi, a opção "LLM do Gambi" fica desabilitada e a dica vem do Minimax.

## Com LLM (Gambi)

São três terminais, que ficam abertos enquanto você joga, e nesta ordem.

### 1. Hub

```bash
gambi hub serve --host 127.0.0.1 --port 3000
```

Só o `dama serve` fala com o hub, então `127.0.0.1` basta: o hub não fica exposto na rede.

### 2. Sala e participante

Num segundo terminal, crie a sala:

```bash
gambi room create --name Dama --hub http://127.0.0.1:3000 --no-interactive
```

A resposta traz o código da sala (seis caracteres, como `ABC123`). Com ele, entre com um participante que serve um modelo do Ollama:

```bash
gambi participant join --room ABC123 --participant-id ollama-1 --nickname Ollama --model llama3.2:latest --endpoint http://127.0.0.1:11434 --hub http://127.0.0.1:3000 --no-interactive
```

O `--model` precisa ser o nome exato que aparece em `ollama list`, com a etiqueta (`llama3.2:latest`, não `llama3.2`). Esse terminal fica preso mostrando "Press Ctrl+C to leave".

### 3. Configuração e servidor do jogo

Copie o `.env.example` para `.env` (uma vez só) e ajuste as duas linhas do Gambi com o código da sala:

```bash
Copy-Item .env.example .env
```

```
DAMA_GAMBI_HUB=http://127.0.0.1:3000
DAMA_GAMBI_SALA=ABC123
```

As outras linhas do `.env` são os valores padrão e podem ficar como estão. O `.env` não entra no git.

Confira o caminho inteiro antes de jogar. O comando também aquece o modelo, que pode levar mais de um minuto na primeira resposta:

```bash
uv run dama checar-gambi
```

Com a resposta "ok" do participante, suba o jogo num terceiro terminal:

```bash
uv run dama serve
```

Na página, "LLM do Gambi" passa a poder ser escolhida, e a "Dica" vem da LLM com a análise do Minimax.

### O que lembrar

- **O código da sala muda quando o hub reinicia.** A sala vive na memória do hub. Reiniciou o hub: crie a sala de novo, entre com o participante, troque `DAMA_GAMBI_SALA` no `.env` e reinicie o `dama serve`.
- **O `dama serve` lê o `.env` só ao subir.** Mudou o `.env`: reinicie o servidor.
- **Se a LLM falhar, o Minimax joga no lugar.** A partida não trava; na lista de lances aparece "Minimax (a LLM falhou)".
- **A justificativa da LLM pode estar errada.** O lance é sempre legal, porque ela só escolhe um número da lista de lances legais, mas o texto que ela escreve nem sempre descreve o que o lance faz.

## Se não abrir no telefone

- Digite o endereço com `https://` na frente e a porta `:8443`.
- O telefone precisa estar no mesmo Wi-Fi do PC, não nos dados móveis nem em rede de convidados.
- Se a página fica carregando até dar tempo esgotado, o firewall do Windows está barrando a porta. Num PowerShell aberto como administrador:

```bash
New-NetFirewallRule -DisplayName "Dama IA Gambi 8443" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow
```

- Se ainda assim não abrir, veja no roteador se o "isolamento de clientes" (ou "isolamento de AP") está ligado.

## Atualizar o Gambi

O projeto foi validado com o Gambi 0.7.2. A 0.6.0 tinha um defeito que atrapalhava: o `--no-interactive` não funcionava no `participant join`.

Veja a versão instalada:

```bash
gambi --version
```

Feche tudo o que estiver usando o Gambi (hub e participantes) e rode o atualizador:

```bash
gambi self update --yes
```

Confira de novo com `gambi --version`. Se mostrar a versão nova, acabou.

### Se a versão não mudar (Windows)

Foi o que aconteceu na passagem da 0.6.0 para a 0.7.2: o atualizador baixou o programa novo, mas não conseguiu trocar o arquivo, porque no Windows um `.exe` em uso não pode ser substituído. O arquivo novo fica ao lado do antigo, com um nome temporário. A troca é feita à mão:

1. Abra a pasta de instalação e veja os arquivos, inclusive os ocultos:

```bash
Get-ChildItem -Force $env:LOCALAPPDATA\gambi
```

Devem aparecer o `gambi.exe` (antigo) e um arquivo como `.gambi.exe.tmp-12345` (o novo, baixado pelo atualizador). O número no final muda a cada vez.

2. Confira que nenhum Gambi está rodando. O comando não deve listar nada:

```bash
Get-Process gambi -ErrorAction SilentlyContinue
```

3. Guarde o antigo como cópia de segurança e ponha o novo no lugar, trocando `12345` pelo número que apareceu no passo 1:

```bash
Rename-Item $env:LOCALAPPDATA\gambi\gambi.exe gambi-antigo.exe.bak
```

```bash
Rename-Item $env:LOCALAPPDATA\gambi\.gambi.exe.tmp-12345 gambi.exe
```

4. Confira:

```bash
gambi --version
```

Se algo der errado, apague o `gambi.exe` novo e renomeie o `gambi-antigo.exe.bak` de volta para `gambi.exe`. Quando a versão nova estiver funcionando, a cópia de segurança pode ser apagada.

### Depois de atualizar

Rode a checagem do projeto contra o hub novo, com hub, sala e participante no ar:

```bash
uv run dama checar-gambi
```

Se a versão for mais nova que a 0.7.2 e a checagem passar, atualize o número em [README.md](../README.md) e [AGENTS.md](../AGENTS.md).
