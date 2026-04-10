from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from cortex_claude.core.engine import CortexEngine
from cortex_claude.server.config import CortexConfig
from cortex_claude.server.tools.recall import handle_recall
from cortex_claude.server.tools.save import handle_save

mcp = FastMCP("cortex-claude")
engine: CortexEngine | None = None


def _get_engine() -> CortexEngine:
    if engine is None:
        _init_engine()
    return engine


def _init_engine() -> None:
    global engine
    base_path = Path(
        os.environ.get("CORTEX_HOME", str(Path.home() / ".cortex-claude"))
    ).expanduser()
    config = CortexConfig.load(base_path)
    engine = CortexEngine(base_path=config.base_path)


def _cwd() -> str:
    return os.getcwd()


@mcp.tool()
async def cortex_save(
    content: str,
    tags: list[str] | None = None,
    scope: str | None = None,
) -> str:
    """Save information to persistent memory.

    Stores content with automatic embedding generation for semantic search.
    Use 'global' scope for cross-project memories.
    """
    return await handle_save(_get_engine(), content, _cwd(), tags, scope)


@mcp.tool()
async def cortex_recall(
    query: str,
    max_tokens: int = 200,
    scope: str | None = None,
) -> str:
    """Recall relevant memories using semantic search.

    Searches stored memories by meaning, not just keywords.
    Returns the most relevant results within the token budget.
    """
    return await handle_recall(_get_engine(), query, _cwd(), max_tokens, scope)


