---
title: Configuration
description: Every Cortex setting in ~/.cortex-claude/config.json - recall, embedding models, fact extraction, decay, deduplication, scopes, clustering and storage.
---

# Configuration

Cortex reads `~/.cortex-claude/config.json`. Every field is optional; anything you leave out uses the default. The repository's [`examples/`](https://github.com/rafaelaugustos/cortex-claude/tree/main/examples) folder has ready-made files.

```json
{
  "recall": {
    "default_max_tokens": 200,
    "default_depth": "auto",
    "sufficiency": {
      "coverage_threshold": 0.7,
      "confidence_threshold": 0.6
    }
  },
  "embeddings": {
    "model": "all-MiniLM-L6-v2",
    "batch_size": 32
  },
  "facts": {
    "extraction_method": "local",
    "min_confidence": 0.5,
    "claude_fallback": false,
    "claude_confidence_threshold": 0.5
  },
  "decay": {
    "lambda": 0.05,
    "recalculate_interval_hours": 6,
    "min_score": 0.01
  },
  "deduplication": {
    "similarity_threshold": 0.92,
    "merge_strategy": "append"
  },
  "scopes": {
    "mappings": {},
    "default": "global",
    "search_order": "project_first"
  },
  "storage": {
    "max_db_size_mb": 500
  }
}
```

## Recall

`default_max_tokens` and `default_depth` apply when Claude does not pass them. The `sufficiency` thresholds decide when a layer answers well enough to stop; raise them and recall goes deeper more often.

## Embeddings

The model used for meaning-based search. The default is fast and small; bigger ones understand more and cost more memory.

| Model | Size | |
| --- | --- | --- |
| `all-MiniLM-L6-v2` | 384 dimensions, 80 MB | Fast (default) |
| `BAAI/bge-small-en-v1.5` | 384 dimensions, 130 MB | Fast |
| `all-mpnet-base-v2` | 768 dimensions, 420 MB | Medium |
| `BAAI/bge-base-en-v1.5` | 768 dimensions, 440 MB | Medium |
| `intfloat/multilingual-e5-small` | 384 dimensions, 470 MB | Multilingual |
| `BAAI/bge-large-en-v1.5` | 1024 dimensions, 1.3 GB | Best quality |
| `intfloat/e5-large-v2` | 1024 dimensions, 1.3 GB | Best quality |

Cortex detects the dimensions by itself.

## Facts

`min_confidence` drops weak facts. `claude_fallback` turns on [Claude-assisted extraction](./privacy#claude-assisted-extraction) when local extraction finds too little.

## Decay

How fast unused memories fade: higher `lambda`, faster fading. Scores are recalculated every `recalculate_interval_hours`. See [How recall works](./how-it-works#freshness).

## Deduplication

Memories more similar than `similarity_threshold` are merged.

## Scopes

Folder-to-scope `mappings`, the `default` scope and the `search_order`. See [Scopes](./scopes).

## Clustering

The `similarity_threshold` for [clusters](./clusters) (0.70 by default).

## Storage

`max_db_size_mb` caps the size of the database.
