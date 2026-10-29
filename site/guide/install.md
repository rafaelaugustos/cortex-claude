---
title: Install and update
description: Install Cortex with uv or pip, run cortex-claude setup to connect it to Claude Code, and upgrade or configure it by hand.
---

# Install and update

Cortex needs **Python 3.11 to 3.13**. It depends on spaCy and PyTorch, which do not have wheels for every Python, so the easiest way is [uv](https://docs.astral.sh/uv/), which brings a compatible Python of its own.

## Install

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install "cortex-claude[code]" --python 3.12
cortex-claude setup
```

The `[code]` extra adds the tree-sitter parsers for the [code graph](./code-graph). Without it, everything else works.

Then restart Claude Code. Cortex works in every project; there is nothing to configure per project.

### What setup does

`cortex-claude setup` prints a pass or fail line for each step, and is safe to run again if something failed (a model download blocked by a proxy, for example):

1. Creates the data folder, `~/.cortex-claude`.
2. Installs the [hooks](./capture) and registers them in `~/.claude/settings.json`.
3. Registers the MCP server as `cortex` in `~/.claude.json`, for all projects.
4. Adds a Cortex section to `~/.claude/CLAUDE.md` (or creates it), telling Claude to use its memory.
5. Downloads the embedding model (about 80 MB) and the spaCy model (about 12 MB).
6. Starts the background daemon.

## Optional extras

| Extra | Adds |
| --- | --- |
| `code` | The code graph (tree-sitter parsers for Python, JavaScript, TypeScript, Go, Java, Swift, Kotlin) |
| `claude` | Claude-assisted fact extraction, off by default (see [Privacy](./privacy#claude-assisted-extraction)) |

Combine them: `uv tool install "cortex-claude[code,claude]" --python 3.12`.

## Upgrade

`uv tool install` does nothing if Cortex is already installed. To get a new version:

```sh
uv tool upgrade cortex-claude
cortex-claude setup
```

## With pip

```sh
pip install "cortex-claude[code]" && cortex-claude setup
```

Use a Python between 3.11 and 3.13. Most install errors come from a newer system Python or a `pip` without spaCy and PyTorch wheels; uv avoids both.

## Manual MCP configuration

To add Cortex to a single project instead, put a `.mcp.json` at its root, pointing at the installed command (`which cortex-claude`):

```json
{
  "mcpServers": {
    "cortex": {
      "type": "stdio",
      "command": "cortex-claude",
      "args": []
    }
  }
}
```

## Commands

| Command | Does |
| --- | --- |
| `cortex-claude` | Runs the MCP server (Claude Code starts it) |
| `cortex-claude setup` | Installs or repairs the integration |
| `cortex-claude daemon` | Runs the background daemon |
| `cortex-claude web [port]` | Opens the [dashboard](./dashboard), on port 37800 by default |

## Where the data lives

Everything is in `~/.cortex-claude`: the databases (one per [scope](./scopes)), the configuration and the hooks. Set `CORTEX_HOME` to use another folder.
