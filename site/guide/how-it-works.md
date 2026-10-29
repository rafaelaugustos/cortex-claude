---
title: How recall works
description: How Cortex saves and recalls memories. Embeddings, fact extraction and summaries on save, three-layer progressive recall, depth modes, hybrid search, deduplication and decay.
---

# How recall works

## Saving

```text
content → embedding + fact extraction + summary → SQLite
```

When something is saved, Cortex:

1. strips anything inside `<private>…</private>` (see [Privacy](./privacy));
2. computes an embedding for meaning-based search;
3. extracts facts into the [knowledge graph](./knowledge-graph);
4. writes a summary, about a quarter of the original;
5. checks for near-duplicates and merges them (cosine similarity above 0.92).

The [daemon](./capture#the-daemon) keeps the embedding model loaded, so a save takes about 0.3 seconds instead of five.

## Recalling

```text
1. Facts      a few tokens each      → enough? stop
2. Summaries  ~25% of the original   → enough? stop
3. Full text  the original           → return
```

`cortex_recall` starts at the cheapest layer and only goes further when the answer is not covered. In practice, most questions stop at the facts.

### Depth

| Depth | Returns | Use it for |
| --- | --- | --- |
| `auto` | Starts cheap, goes further if needed | Most questions (the default) |
| `facts` | Knowledge graph triplets only | Quick lookups |
| `summaries` | Facts and summaries | Some detail |
| `full` | Everything, including the original text | When the details matter |

`max_tokens` (200 by default) caps how much comes back.

## Search

Recall combines two searches:

- **vector similarity**, for meaning: "token expiry" finds "JWT lifetime";
- **SQLite FTS5**, for exact words: names, flags, error codes.

## Freshness

Memories you never recall lose relevance over time; the ones you use gain it:

```text
score = e^(-λ · days) · (1 + log(access_count))
```

Scores are recalculated when the server starts and every few hours. Tune `λ` in [configuration](./configuration#decay).

## About the numbers

Token counts are estimates. Claude's tokenizer is not public, so Cortex counts with OpenAI's `tiktoken` (`cl100k_base`) as a stand-in: close enough to budget recall, not exact. In a small benchmark of 10 memories, `facts` and `auto` returned 66% fewer tokens than `full`. Run it yourself with `uv run python scripts/benchmark.py` from a clone.
