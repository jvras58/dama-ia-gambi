# Constituição do projeto

Princípios que valem para todas as funcionalidades. Uma spec, um plano ou um código que contrarie um deles precisa de um ADR justificando.

## 1. A especificação vem antes do código

Toda funcionalidade passa por `spec.md` → `plan.md` → `tasks.md` antes de qualquer implementação. Mudança de requisito altera primeiro a spec. Ver [ADR 0001](adr/0001-adotar-sdd-e-estrutura-de-documentos.md).

## 2. O estado do jogo é sempre legal

Nenhuma fonte externa altera o jogo diretamente. Câmera e LLM só **propõem**; o motor de regras é a única autoridade sobre o que é um lance válido. Uma leitura estranha da câmera ou uma resposta ruim da LLM nunca resulta em posição ilegal.

## 3. A partida nunca trava por causa de terceiros

Falha de LLM, do hub Gambi ou de rede tem sempre um caminho de continuação (nova tentativa, fallback, correção manual) e fica visível para o usuário.

## 4. Núcleo puro e testável sem hardware

Regras e Minimax são Python puro, sem I/O. Visão é testada com imagens gravadas; LLM, com um servidor falso. Tudo o que pode ser verificado sem câmera e sem hub tem teste automatizado.

## 5. Local e privado por padrão

Tudo funciona na rede local, sem internet. Imagens da câmera não são gravadas em disco, salvo com uma opção de depuração explícita. Nada é exposto à internet.

## 6. Simples primeiro

A solução mais simples que atende ao requisito entra primeiro; a mais sofisticada só entra com medição que mostre a necessidade. Exemplos: cor calibrada antes de modelo treinado; Python puro antes de otimização.

## 7. Honestidade sobre incerteza

Toda leitura da câmera tem confiança, todo lance de IA informa sua origem (LLM, Minimax ou fallback), e a avaliação do juiz é apresentada como opinião de um motor limitado.

## 8. Português

Documentos, interface e nomes de domínio no código (`tabuleiro`, `lance`, `dama`) em português do Brasil.
