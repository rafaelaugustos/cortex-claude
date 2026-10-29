---
title: The knowledge graph
description: How Cortex turns memories into subject, relation, object facts with spaCy and patterns, normalizes entities, merges facts, tracks time and confidence, and walks connections.
---

# The knowledge graph

Every memory is broken into **facts**: a subject, a relation and an object.

<div class="facts">
  <Fact s="api" p="uses" o="rate limiting" />
  <Fact s="auth service" p="uses" o="jwt tokens" />
  <Fact s="refresh tokens" p="stored_in" o="httponly cookies" />
</div>

Facts are the cheapest layer of [recall](./how-it-works): a few tokens each, and often all Claude needs.

## Extraction

Three methods together:

1. **spaCy NLP:** dependency parsing, named entities, passive voice, lists joined by "and".
2. **Patterns:** bullet lists (`- X for Y`), `key: value`, comma lists, slashes (`React/TypeScript`), parentheses (`FastAPI (Python)`).
3. **Claude**, optional and off by default: when local extraction finds fewer than two confident facts, it can ask Claude Haiku. See [Privacy](./privacy#claude-assisted-extraction).

English and Portuguese are detected automatically. Spanish, German and French work with their spaCy models installed.

## Entities

Names are normalized so the same thing is one entity: `postgres`, `PostgreSQL` and `pg` become `postgresql`; `js` becomes `javascript`; `k8s` becomes `kubernetes`.

## Facts that grow up

- **Merging:** when several memories state the same fact, it becomes one fact with more confidence.
- **Confidence:** facts gain confidence when they are used, and lose it when newer information contradicts them.
- **Time:** facts notice when something happened ("in April 2024", "yesterday", "since v2") and keep the date.

## Walking the graph

`cortex_traverse` follows connections across hops:

```text
auth → jwt → express-jwt → middleware
  ↓
  httponly cookies
```

Ask Claude *"what's connected to auth?"* and it can find things you never asked about directly. Start from a [cluster](./clusters) with `start="cluster:42"`.
