# Cortex Claude

Local-first, token-efficient memory system for Claude Code via MCP.

## What is this?

Cortex Claude gives Claude Code persistent memory through a local MCP server. Unlike other memory solutions that dump everything into context, Cortex uses **progressive recall** — a 3-layer retrieval system that returns only what's relevant, using the minimum tokens needed.

Save once:
> "The auth service uses JWT tokens with 24-hour expiry. Refresh tokens are stored in httpOnly cookies."

Ask later, get back only what matters:

```
# Layer 1: Facts (cheapest — ~7 tokens each)
auth service → use → jwt tokens
auth service → use → hour expiry

# Layer 2: Summary (~25% of original)
# Layer 3: Full content (only if needed)
```

### Key Features

- **Progressive recall** — 3 layers (facts → summaries → full content), stops at the cheapest sufficient layer
- **Knowledge graph** — auto-extracts structured facts via spaCy NLP with multi-hop traversal
- **Token efficient** — 66%+ fewer tokens vs. full content retrieval (benchmarked)
- **Local-first** — SQLite + local embeddings + local NLP. Zero API calls, zero network, zero cost
- **Graph traversal** — navigate entity connections across multiple hops (A → B → C)
- **Entity normalization** — "postgres", "PostgreSQL", "pg" all resolve to the same entity
- **Configurable scopes** — global, per-project, or custom memory boundaries
- **Deduplication** — detects and merges near-identical memories automatically
- **Decay system** — unused memories lose relevance over time, keeping results fresh
- **Multi-language** — fact extraction and summarization in EN, PT (auto-detected). ES, DE, FR supported with spaCy models
- **Full-text search** — FTS5 keyword search alongside semantic vector search
- **Fully configurable** — all thresholds, ratios, and behaviors customizable via config.json
- **On-demand** — Claude calls memory tools only when needed, nothing auto-injected

### Benchmarks

With 10 stored memories (244 total tokens):

| Depth | Tokens returned | Reduction | Latency |
|-------|----------------|-----------|---------|
| `facts` | 82 | **66%** | ~10ms |
| `auto` | 82 | **66%** | ~10ms |
| `full` | 244 | 0% | ~12ms |

Facts query: **0.1ms**. Graph traversal: **0.2ms**. Save: **~30ms** (after model load).

## Quick Start

### Install

```bash
pip install cortex-claude
```

### Configure Claude Code

Add a `.mcp.json` to your project root (or `~/.claude.json` for global):

```json
{
  "mcpServers": {
    "cortex": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "cortex_claude"]
    }
  }
}
```

First run downloads the embedding model (~80MB) and spaCy model (~12MB) automatically.

### Use

In any Claude Code session:

```
"Remember that the API uses rate limiting at 500 req/min"
→ cortex_save stores it, extracts facts, generates embedding

"What do you know about rate limiting?"
→ cortex_recall finds it via progressive recall

"What facts do you have about the API?"
→ cortex_facts returns structured knowledge graph triplets

"What's connected to the auth service?"
→ cortex_traverse follows graph connections across hops

"Forget what I said about the old API key"
→ cortex_forget removes matching memories (with preview first)

"Show me the memory status"
→ cortex_status shows totals, scopes, storage size
```

## Tools

| Tool | What it does | Token cost |
|------|-------------|------------|
| `cortex_save` | Store memory with auto fact extraction, summarization, and embedding | N/A |
| `cortex_recall` | Progressive retrieval: facts → summaries → full content | Controlled via `max_tokens` budget |
| `cortex_facts` | Direct knowledge graph query, returns structured triplets | ~5-15 tokens per fact |
| `cortex_traverse` | Navigate the knowledge graph across multiple hops | ~5-15 tokens per connection |
| `cortex_forget` | Delete memories by query or ID. Dry-run by default (preview before deleting) | N/A |
| `cortex_scopes` | Manage scopes: list, create, delete, link/unlink directories | N/A |
| `cortex_status` | Dashboard: memory count, fact count, storage size per scope | N/A |

### cortex_recall depth modes

| Mode | Returns | When to use |
|------|---------|------------|
| `auto` | Starts cheap, escalates if needed | Default — best for most queries |
| `facts` | Only knowledge graph triplets | Quick lookups, minimal token use |
| `summaries` | Facts + compressed summaries | Medium detail needed |
| `full` | All layers including original text | Full context needed |

## How It Works

```
Save: content → embedding + fact extraction (spaCy) + summarization → SQLite

Recall (progressive):
  1. Facts layer     (~5-15 tokens/fact)   → sufficient? stop
  2. Summaries layer (~25% of original)    → sufficient? stop
  3. Full chunks     (original content)    → return
```

**Fact extraction** uses spaCy dependency parsing and NER to produce subject-relation-object triplets. Runs locally, costs zero tokens. Entities are normalized and deduplicated ("postgres" → "postgresql").

**Graph traversal** navigates entity connections across multiple hops. Query "auth" and discover: auth → JWT → express-jwt → middleware.

**Summarization** uses extractive summarization (sentence scoring via TF-IDF + entity density + position). No LLM calls. Multi-language aware (EN/PT).

**Deduplication** detects near-identical memories (cosine similarity threshold, configurable) and merges them.

**Decay** — memories that aren't accessed lose relevance over time (`score = e^(-λ * days) * (1 + log(access_count))`). Recalculated on server startup. Affects ranking in all recall layers.

**Hybrid search** — combines vector similarity (semantic) + FTS5 (keyword exact match) for best recall. FTS5 synced automatically via SQLite triggers.

**Scopes** isolate memories per project. Manage via `cortex_scopes` tool or configure in `~/.cortex-claude/config.json`.

## Configuration

All behavior is customizable via `~/.cortex-claude/config.json`:

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
    "min_confidence": 0.5
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
    "mappings": {
      "/path/to/project-a": "project:a",
      "/path/to/project-b": "project:b"
    },
    "default": "global",
    "search_order": "project_first"
  },
  "storage": {
    "max_db_size_mb": 500
  }
}
```

All fields are optional. Defaults are used for anything not specified.

## Development

```bash
git clone https://github.com/your-user/cortex-claude.git
cd cortex-claude
uv venv --python python3.13
uv sync --all-extras
uv run python -m spacy download en_core_web_sm
uv run pytest
```

Run the demo:

```bash
uv run python scripts/demo.py
```

Run benchmarks:

```bash
uv run python scripts/benchmark.py
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical specification.

## License

MIT
