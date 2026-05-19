from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from cortex_claude.core.engine import CortexEngine
from cortex_claude.server.config import CortexConfig
from cortex_claude.server.tools.clusters import handle_clusters
from cortex_claude.server.tools.code import handle_code, handle_index_code
from cortex_claude.server.tools.facts import handle_facts
from cortex_claude.server.tools.forget import handle_forget
from cortex_claude.server.tools.recall import handle_recall
from cortex_claude.server.tools.save import handle_save
from cortex_claude.server.tools.scopes import handle_scopes
from cortex_claude.server.tools.status import handle_status
from cortex_claude.server.tools.traverse import handle_traverse

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
    engine = CortexEngine(config=config)
    engine.initialize()


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


@mcp.tool()
async def cortex_traverse(
    start: str,
    max_hops: int = 2,
    scope: str | None = None,
) -> str:
    """Traverse the knowledge graph from an entity or cluster.

    Follows connections through multiple hops to discover related information.
    - Entity: 'auth' → 'JWT' → 'express-jwt' (2 hops).
    - Cluster: 'cluster:42' seeds the traversal from the most-central memories
      of cluster 42 (use cortex_clusters to find IDs).
    """
    return await handle_traverse(_get_engine(), start, _cwd(), max_hops, scope)


@mcp.tool()
async def cortex_forget(
    query: str | None = None,
    memory_id: str | None = None,
    scope: str | None = None,
    dry_run: bool = True,
) -> str:
    """Remove memories from storage.

    By default runs in dry_run mode (preview only).
    Set dry_run=false to actually delete.
    """
    return await handle_forget(_get_engine(), _cwd(), query, memory_id, scope, dry_run)


@mcp.tool()
async def cortex_scopes(
    action: Literal["list", "create", "delete", "link", "unlink", "info"],
    name: str | None = None,
    path: str | None = None,
) -> str:
    """Manage memory scopes.

    Actions: list, create, delete, link (directory to scope), unlink, info.
    """
    return await handle_scopes(_get_engine(), action, _cwd(), name, path)


@mcp.tool()
async def cortex_status(
    scope: str | None = None,
) -> str:
    """Show Cortex memory statistics.

    Returns total memories, facts, scopes, storage size.
    """
    return await handle_status(_get_engine(), _cwd(), scope)


@mcp.tool()
async def cortex_code(
    symbol: str,
    scope: str | None = None,
) -> str:
    """Look up a code symbol in the knowledge graph.

    Returns: definition file/line, language, what it calls, who calls it,
    what it extends, imports, and which memories mention it.
    Use this BEFORE reading a file if you only need to understand a function/class.
    Token cost: ~50-150 vs ~1000+ for reading the whole file.
    """
    return await handle_code(_get_engine(), _cwd(), symbol, scope)


@mcp.tool()
async def cortex_index_code(
    path: str,
    scope: str | None = None,
    recursive: bool = True,
) -> str:
    """Index a file or directory into the code knowledge graph.

    Walks the path (recursively by default), parses each supported source file
    via tree-sitter, and stores symbols/calls/imports as facts. Supported:
    Python, JS/TS, Go, Java, Swift, Kotlin. Skips node_modules, __pycache__,
    build/dist/.venv/target by default.
    """
    return await handle_index_code(_get_engine(), _cwd(), path, scope, recursive)


@mcp.tool()
async def cortex_clusters(
    action: Literal["list", "backfill"] = "list",
    scope: str | None = None,
    limit: int = 50,
) -> str:
    """List or rebuild memory clusters (sub-graphs that form automatically by similarity).

    Actions:
      - 'list' (default): show existing clusters with their labels and sizes.
      - 'backfill': wipe and re-cluster all memories in the scope from scratch.
        Use this once after enabling clustering, or after tuning similarity_threshold.

    Each scope's memories are grouped by semantic similarity. Labels are derived
    from the most frequent entities in each cluster's facts.
    """
    return await handle_clusters(_get_engine(), _cwd(), action, scope, limit)
