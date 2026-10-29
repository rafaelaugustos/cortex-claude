---
layout: home
title: Local memory for Claude Code
description: Cortex gives Claude Code a persistent memory through a local MCP server. Progressive recall returns only what is relevant, from a knowledge graph and a code graph stored in SQLite on your machine.

hero:
  name: Cortex
  text: Memory that remembers what matters.
  tagline: A local MCP server that gives Claude Code a memory. It answers from structured facts first and only reads more when it has to. Open source, on SQLite, on your machine.
  image:
    src: /images/cortex.webp
    width: 320
    height: 320
    fetchpriority: high
    decoding: async
    alt: The Cortex icon, a black and tan puppy with a pink bow on a purple square.
  actions:
    - theme: brand
      text: Get started
      link: /guide/
    - theme: alt
      text: Install
      link: /guide/install
    - theme: alt
      text: GitHub
      link: https://github.com/rafaelaugustos/cortex-claude

features:
  - title: Progressive recall
    details: Facts first, then summaries, then the full text, stopping at the cheapest layer that answers. Claude reads tens of tokens instead of your whole memory.
    link: /guide/how-it-works
    linkText: How recall works
  - title: A knowledge graph
    details: Every memory becomes subject, relation, object facts. "postgres", "PostgreSQL" and "pg" are one entity, and you can walk the connections.
    link: /guide/knowledge-graph
    linkText: The knowledge graph
  - title: A code graph
    details: Functions, classes, calls and imports from seven languages in the same graph. Ask for a symbol and get its definition, callers and callees.
    link: /guide/code-graph
    linkText: The code graph
  - title: Works on its own
    details: Hooks capture what Claude does, keep what matters, and tell Claude it has a memory when a session starts. Nothing to configure per project.
    link: /guide/capture
    linkText: Hooks and auto-capture
  - title: Local first
    details: SQLite, local embeddings and local NLP. No account, no API calls, no cost. Wrap anything in a private tag and it never gets saved.
    link: /guide/privacy
    linkText: Privacy
  - title: See your memory
    details: A dashboard on localhost to browse clusters, follow entities, search memories and clean up in bulk with a preview.
    link: /guide/dashboard
    linkText: The dashboard
---

<section class="home-section">

## Save once, ask later

Tell Claude *"the auth service uses JWT tokens with a 24-hour expiry"*. Cortex keeps the text, a summary, and facts like these:

<div class="facts">
  <Fact s="auth service" p="uses" o="jwt tokens" />
  <Fact s="auth service" p="uses" o="hour expiry" />
</div>

Ask *"what do you know about auth?"* weeks later and the facts are often enough. The summary and the full text are only read when they are not.

</section>
