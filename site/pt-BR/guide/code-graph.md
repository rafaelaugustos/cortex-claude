---
title: O grafo de código
description: O Cortex indexa funções, classes, chamadas e imports de Python, JavaScript, TypeScript, Go, Java, Swift e Kotlin no grafo, para o Claude procurar um símbolo em vez de ler arquivos.
---

# O grafo de código

Com o extra `code` instalado, o Cortex lê o seu código com tree-sitter e guarda os símbolos como fatos no mesmo grafo das suas memórias:

<div class="facts">
  <Fact s="my_func" p="defined_in" o="app/jobs.py:42" />
  <Fact s="my_func" p="calls" o="other_func" />
  <Fact s="MyClass" p="extends" o="BaseClass" />
  <Fact s="sample" p="imports" o="json" />
</div>

**Linguagens:** Python, JavaScript, TypeScript e TSX, Go, Java, Swift e Kotlin.

## Procurando um símbolo

O `cortex_code(symbol)` devolve onde ele está definido, o que ele chama, quem chama ele, o que ele estende e importa, e quais memórias falam dele, em uns 50 a 150 tokens. Ler o arquivo para achar a mesma coisa custa mil ou mais.

## Mantendo indexado

- **No começo de uma sessão** num projeto que o Cortex ainda não indexou, o hook pede ao daemon para indexar em segundo plano, até 2.000 arquivos. Acontece uma vez por projeto.
- **Conforme o Claude lê e edita** arquivos de código, eles são indexados de novo, e o grafo fica em dia.
- **Na mão:** peça ao Claude para indexar uma pasta, o que chama o `cortex_index_code(path)`.

Quando um projeto não tem [escopo](./scopes) próprio, o código dele vai para um escopo automático `project:<nome-da-pasta>` em vez do global.

## Decisões ligadas ao código

Quando uma memória salva fala de um símbolo que o Cortex conhece, ele adiciona um fato `mentions`, ligando a decisão ou o relato de bug ao código de que ela trata. O `cortex_code` passa a mostrar essa memória junto com o símbolo.
