---
title: Ferramentas MCP
description: As dez ferramentas MCP que o Cortex dá ao Claude Code - save, recall, facts, traverse, code, index_code, clusters, forget, scopes e status - com os argumentos.
---

# Ferramentas MCP

O Claude Code enxerga dez ferramentas. Você não chama elas; você pede ao Claude, e ele escolhe a ferramenta. Conhecer ajuda a pedir bem.

| Ferramenta | Faz |
| --- | --- |
| `cortex_save` | Salva uma memória, com fatos, resumo e embedding |
| `cortex_recall` | Recall progressivo: fatos, depois resumos, depois texto inteiro |
| `cortex_facts` | Busca fatos sobre um assunto no grafo de conhecimento |
| `cortex_traverse` | Anda pelo grafo a partir de uma entidade ou de um cluster |
| `cortex_code` | A definição, quem chama, o que chama e as menções de um símbolo |
| `cortex_index_code` | Indexa um arquivo ou uma pasta no grafo de código |
| `cortex_clusters` | Lista ou reconstrói os clusters de memória |
| `cortex_forget` | Apaga memórias, como simulação por padrão |
| `cortex_scopes` | Lista, cria, apaga, liga e desliga escopos |
| `cortex_status` | Contagem de memórias e fatos e o espaço por escopo |

## Argumentos

### cortex_save

| Argumento | |
| --- | --- |
| `content` | O que lembrar |
| `tags` | Lista de tags, opcional |
| `scope` | Opcional; senão, o [escopo](./scopes) atual |

### cortex_recall

| Argumento | Padrão |
| --- | --- |
| `query` | |
| `depth` | `auto` (ou `facts`, `summaries`, `full`) |
| `max_tokens` | `200` |
| `scope` | o atual |

### cortex_facts

`topic` e, opcionalmente, `relation`, `scope` e `limit` (20). Devolve trios, poucos tokens cada.

### cortex_traverse

`start` é uma entidade, ou `cluster:<id>` para começar de um [cluster](./clusters). O `max_hops` padrão é 2.

### cortex_code e cortex_index_code

`cortex_code(symbol)` procura um símbolo. `cortex_index_code(path)` indexa um arquivo ou, com `recursive` (o padrão), uma pasta. Veja [O grafo de código](./code-graph).

### cortex_clusters

`action` é `list` (o padrão) ou `backfill`, que reconstrói os clusters. O `limit` padrão é 50.

### cortex_forget

Apaga por `query` ou por `memory_id`. **O `dry_run` vem ligado**: ele mostra o que sairia. O Claude precisa pedir de novo com `dry_run=false` para apagar.

### cortex_scopes

`action` é `list`, `info`, `create`, `delete`, `link` ou `unlink`, com um `name` e, para ligar, um `path`.

### cortex_status

Opcionalmente para um `scope`.
