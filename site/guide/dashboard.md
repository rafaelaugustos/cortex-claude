---
title: The dashboard
description: The Cortex web dashboard on localhost - a cluster map, entity neighborhoods, a memory browser, bulk cleanup with a preview and live stats.
---

# The dashboard

```sh
cortex-claude web
```

Opens your memory at `http://localhost:37800` (pass another port as an argument).

The dashboard works the way recall does, cheapest layer first. It never draws the whole graph at once, so it stays fast with tens of thousands of facts.

## What is in it

- **Cluster map:** the landing view shows your [clusters](./clusters), sized by how many memories they hold. Open one to see its own graph and its strongest memories.
- **Entity focus:** click a node for its neighborhood, its facts and the memories that mention it.
- **Memory browser:** search, filter by scope and tag, sort by recency, relevance, last use or size.
- **Bulk cleanup:** select by tag, scope, cluster or a regular expression and see exactly what will go before anything is deleted. Deleting a memory removes its facts and its embedding too.
- **Live stats:** memory and fact counts, clusters, storage, and a 30-day chart of what came in, handy to spot the day auto-capture ran away.

## Security

The dashboard listens on localhost only, sends no CORS headers and checks the `Host` and `Origin` of every request, so no other page open in your browser can read or change your memory.
