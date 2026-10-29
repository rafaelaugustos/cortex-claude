---
title: Clusters
description: Cortex groups memories into semantic clusters by embedding similarity, labels them from their most frequent entities, and lets Claude navigate memory top-down.
---

# Clusters

As memories pile up, Cortex groups the ones that are about the same thing into **clusters**, by the similarity of their embeddings. Each cluster is labeled with the entities that show up most in its facts, for example `embeddings, vectors, sqlite-vec`.

Clusters let Claude, and you, navigate memory from the top down: see what topics exist, then go into one.

- `cortex_clusters` lists them, with how many memories each holds.
- `cortex_traverse` with `start="cluster:42"` walks the graph from inside one.
- The [dashboard](./dashboard) opens on a map of them.

## When they update

Clustering runs in the background after every 20 saves, at most once every 5 minutes. To rebuild everything (after changing the threshold, for example), ask for `cortex_clusters` with `action="backfill"`.

## Tuning

`similarity_threshold` (0.70 by default) decides how alike two memories must be to share a cluster. Raise it for tighter clusters, lower it for fewer singletons. See [Configuration](./configuration).
