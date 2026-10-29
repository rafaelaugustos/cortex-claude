---
layout: home
title: Memória local para o Claude Code
description: O Cortex dá ao Claude Code uma memória que dura entre sessões, por um servidor MCP local. O recall progressivo devolve só o que importa, de um grafo de conhecimento e de um grafo de código guardados em SQLite na sua máquina.

hero:
  name: Cortex
  text: Memória que lembra do que importa.
  tagline: Um servidor MCP local que dá memória ao Claude Code. Ele responde primeiro com fatos estruturados e só lê mais quando precisa. Open source, em SQLite, na sua máquina.
  image:
    src: /images/cortex.webp
    width: 320
    height: 320
    fetchpriority: high
    decoding: async
    alt: O ícone do Cortex, um filhote preto e caramelo com um laço rosa num quadrado roxo.
  actions:
    - theme: brand
      text: Começar
      link: /pt-BR/guide/
    - theme: alt
      text: Instalar
      link: /pt-BR/guide/install
    - theme: alt
      text: GitHub
      link: https://github.com/rafaelaugustos/cortex-claude

features:
  - title: Recall progressivo
    details: Primeiro os fatos, depois os resumos, depois o texto inteiro, parando na camada mais barata que responde. O Claude lê dezenas de tokens em vez da memória toda.
    link: /pt-BR/guide/how-it-works
    linkText: Como o recall funciona
  - title: Um grafo de conhecimento
    details: Toda memória vira fatos de sujeito, relação e objeto. "postgres", "PostgreSQL" e "pg" são uma entidade só, e dá para andar pelas ligações.
    link: /pt-BR/guide/knowledge-graph
    linkText: O grafo de conhecimento
  - title: Um grafo de código
    details: Funções, classes, chamadas e imports de sete linguagens no mesmo grafo. Peça um símbolo e receba a definição, quem chama e o que ele chama.
    link: /pt-BR/guide/code-graph
    linkText: O grafo de código
  - title: Funciona sozinho
    details: Hooks capturam o que o Claude faz, guardam o que importa e avisam o Claude que ele tem memória quando a sessão começa. Nada para configurar por projeto.
    link: /pt-BR/guide/capture
    linkText: Hooks e captura automática
  - title: Local primeiro
    details: SQLite, embeddings locais e NLP local. Sem conta, sem chamada de API, sem custo. Coloque qualquer coisa numa tag private e ela nunca é salva.
    link: /pt-BR/guide/privacy
    linkText: Privacidade
  - title: Veja a sua memória
    details: Um dashboard no localhost para navegar pelos clusters, seguir entidades, buscar memórias e limpar em lote com prévia.
    link: /pt-BR/guide/dashboard
    linkText: O dashboard
---

<section class="home-section">

## Salve uma vez, pergunte depois

Diga ao Claude *"o serviço de auth usa tokens JWT com validade de 24 horas"*. O Cortex guarda o texto, um resumo e fatos como estes:

<div class="facts">
  <Fact s="auth service" p="uses" o="jwt tokens" />
  <Fact s="auth service" p="uses" o="hour expiry" />
</div>

Pergunte *"o que você sabe sobre auth?"* semanas depois e muitas vezes os fatos bastam. O resumo e o texto inteiro só são lidos quando não bastam.

</section>
