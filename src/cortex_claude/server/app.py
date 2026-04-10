from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from cortex_claude.core.engine import CortexEngine
from cortex_claude.server.config import CortexConfig
from cortex_claude.server.tools.facts import handle_facts
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

    Stores content with automatic embedding generation, fact extraction,
    and summarization. Use 'global' scope for cross-project memories.
    """
    return await handle_save(_get_engine(), content, _cwd(), tags, scope)


@mcp.tool()
async def cortex_recall(
    query: str,
    max_tokens: int = 200,
    scope: str | None = None,
    depth: Literal["auto", "facts", "summaries", "full"] = "auto",
) -> str:
    """Recall relevant memories using progressive retrieval.

    Uses 3-layer search: facts (cheapest) -> summaries -> full content.
    - depth='facts': only knowledge graph triplets (~5-15 tokens each)
    - depth='summaries': facts + compressed summaries
    - depth='full': all layers including original content
    - depth='auto': progressive, stops at cheapest sufficient layer (default)
    """
    return await handle_recall(_get_engine(), query, _cwd(), max_tokens, scope, depth)


@mcp.tool()
async def cortex_facts(
    topic: str,
    relation: str | None = None,
    scope: str | None = None,
    limit: int = 20,
) -> str:
    """Query the knowledge graph directly.

    Returns structured subject-relation-object facts.
    Extremely token-efficient (~5-15 tokens per fact).
    """
    return await handle_facts(_get_engine(), topic, _cwd(), relation, scope, limit)
