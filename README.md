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
- **Knowledge graph** — auto-extracts structured facts via spaCy NLP, not just raw text
- **Token efficient** — 70-90% fewer tokens vs. traditional memory solutions
- **Local-first** — SQLite + local embeddings + local NLP. Zero API calls, zero network, zero cost
- **Configurable scopes** — global, per-project, or custom memory boundaries
- **Deduplication** — detects and merges near-identical memories automatically
- **Multi-language** — fact extraction works in English and Portuguese (auto-detected)
- **On-demand** — Claude calls memory tools only when needed, nothing auto-injected

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
```

## Tools

| Tool | What it does | Token cost |
|------|-------------|------------|
| `cortex_save` | Store memory with auto fact extraction, summarization, and embedding | N/A |
| `cortex_recall` | Progressive retrieval: facts → summaries → full content | Controlled via `max_tokens` budget |
| `cortex_facts` | Direct knowledge graph query, returns structured triplets | ~5-15 tokens per fact |

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

**Fact extraction** uses spaCy dependency parsing and NER to produce subject-relation-object triplets. Runs locally, costs zero tokens.

**Summarization** uses extractive summarization (sentence scoring via TF-IDF + entity density + position). No LLM calls.

**Deduplication** detects near-identical memories (cosine similarity > 0.92) and merges them.

**Scopes** isolate memories per project. Configure in `~/.cortex-claude/config.json`:

```json
{
  "scopes": {
    "mappings": {
      "/path/to/project-a": "project:a",
      "/path/to/project-b": "project:b"
    }
  }
}
```

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

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical specification.

## License

MIT
