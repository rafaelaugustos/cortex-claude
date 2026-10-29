---
title: O que é o Cortex?
description: O Cortex é um servidor de memória MCP local e open source para o Claude Code, com recall progressivo, grafo de conhecimento, grafo de código e captura automática por hooks.
---

# O que é o Cortex?

O Cortex dá ao [Claude Code](https://claude.ai/claude-code) uma memória que dura entre sessões. Ele roda na sua máquina como um servidor MCP, guarda tudo em SQLite e é open source sob a licença MIT.

A maioria das ferramentas de memória injeta uma pilha de anotações em todo prompt. O Cortex faz o contrário: o Claude pergunta, e o Cortex responde com o mínimo possível.

## A ideia

Quando algo é salvo, o Cortex guarda de três jeitos:

<ul class="layers">
  <li><strong>Fatos</strong><span>Trios de sujeito, relação e objeto. Poucos tokens cada.</span></li>
  <li><strong>Resumo</strong><span>Mais ou menos um quarto do original.</span></li>
  <li><strong>Texto inteiro</strong><span>O original, só quando os outros não bastam.</span></li>
</ul>

O recall começa pelos fatos e para na primeira camada que responde a pergunta. Veja [Como o recall funciona](./how-it-works).

## O que mais ele faz

- **[Grafo de conhecimento](./knowledge-graph):** os fatos ligam as entidades, e o Claude pode andar pelas ligações.
- **[Grafo de código](./code-graph):** os símbolos do seu código no mesmo grafo, então "quem chama isso?" custa uns cem tokens em vez de ler arquivos.
- **[Clusters](./clusters):** as memórias se agrupam pelo significado.
- **[Hooks](./capture):** os resultados das ferramentas do Claude Code são capturados, filtrados e salvos sem você pedir.
- **[Escopos](./scopes):** memória global, por projeto ou com os limites que você quiser.
- **[Dashboard](./dashboard):** uma visão web local da sua memória.

## Usando

Depois de [instalar](./install), converse com o Claude normalmente:

```text
Lembra que o limite da API é 500 requisições por minuto.
O que você sabe sobre rate limiting?
O que está ligado ao serviço de auth?
Esquece o que eu disse sobre a chave antiga da API.
```

O Claude decide quando usar as [ferramentas do Cortex](./tools). O setup também coloca instruções no seu `~/.claude/CLAUDE.md` para ele consultar a memória antes de dizer que não sabe.
