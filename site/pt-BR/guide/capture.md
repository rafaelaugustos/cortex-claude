---
title: Hooks e captura automática
description: Os hooks do Claude Code que o Cortex instala - SessionStart, PreToolUse e PostToolUse - o que eles capturam, o filtro que tira o ruído e o daemon em segundo plano.
---

# Hooks e captura automática

O `cortex-claude setup` instala três hooks do Claude Code, para todos os projetos.

## SessionStart

Quando uma sessão abre, o hook avisa o Claude que ele tem memória, com alguns números e fatos conhecidos, lidos direto do SQLite em menos de um segundo. É isso que faz o Claude consultar o Cortex antes de dizer que não sabe.

Ele também pede ao daemon para indexar o projeto no [grafo de código](./code-graph) na primeira vez que você trabalha nele.

## PreToolUse (Bash)

Antes de um comando de shell rodar, o hook troca uma lista curta de comandos verbosos por equivalentes mais enxutos, para o Claude ler menos saída:

| O Claude roda | Vira |
| --- | --- |
| `git status` | `git status --short --branch` |
| `git log` | `git log --oneline -n 20` |

Só comandos exatos e conhecidos são trocados. Um comando com flags próprias passa sem mudança.

## PostToolUse

Depois que uma ferramenta roda, o resultado é capturado em segundo plano: Bash, Read, Edit, Write, Grep, Glob, Agent, WebSearch, WebFetch e as ferramentas de outros servidores MCP. Arquivos de código que o Claude lê ou edita também são indexados no grafo de código.

### O filtro de captura

Nem tudo vale lembrar. Antes de salvar, cada resultado capturado passa por um filtro que olha o tamanho, palavras que indicam algo importante, a ferramenta de onde veio e quantas entidades ele cita. Um `ls`, uma leitura trivial ou uma edição barulhenta ficam de fora. Casos ambíguos podem, se você quiser, ser julgados por um modelo.

As tags `<private>` valem aqui também: veja [Privacidade](./privacy#tags-private).

## O daemon

Um processo pequeno em segundo plano mantém o modelo de embedding carregado e escuta num socket Unix local. Os salvamentos passam por ele, então levam uns 0,3 segundos em vez dos cinco de uma partida a frio. O setup sobe ele; `cortex-claude daemon` roda na mão.
