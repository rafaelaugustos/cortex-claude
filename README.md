# Cortex Claude

Local-first, token-efficient memory system for Claude Code via MCP.

## What is this?

Cortex Claude gives Claude Code persistent memory through a local MCP server. Unlike other memory solutions that dump everything into context, Cortex uses a progressive recall system that returns only what's relevant — using the minimum number of tokens needed.

### Key Features

- **Token efficient** — progressive recall: facts → summaries → full content
- **Local-first** — SQLite + local embeddings, zero network dependencies
- **Configurable scopes** — global, per-project, or custom memory boundaries
- **On-demand** — Claude calls memory tools only when needed, nothing auto-injected
- **Knowledge graph** — stores structured facts, not just raw text

## Quick Start

```bash
pip install cortex-claude
```

Add to your Claude Code MCP config (`~/.claude/claude_code_config.json`):

```json
{
    "mcpServers": {
        "cortex": {
            "command": "python",
            "args": ["-m", "cortex_claude"],
            "env": {
                "CORTEX_HOME": "~/.cortex-claude"
            }
        }
    }
}
```

## How It Works

Cortex exposes two core tools to Claude:

- **`cortex_save`** — stores information with automatic embedding generation
- **`cortex_recall`** — retrieves relevant memories via semantic search within a token budget

Memories are stored in local SQLite databases (one per scope) with vector embeddings for semantic search.

## Development

```bash
git clone https://github.com/your-user/cortex-claude.git
cd cortex-claude
uv sync --all-extras
uv run pytest
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical specification.

## License

MIT
