from __future__ import annotations

from typing import Literal

from cortex_claude.core.engine import CortexEngine
from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.learning.store import LearningStore
from cortex_claude.learning.config import LearningConfig
from cortex_claude.learning.semantic import SemanticClient


async def handle_recall(
    engine: CortexEngine,
    query: str,
    cwd: str,
    max_tokens: int = 200,
    scope: str | None = None,
    depth: Literal["auto", "facts", "summaries", "full"] = "auto",
) -> str:
    max_tokens = max(0, min(max_tokens, 20000))
    config = LearningConfig.load(engine._base_path)
    with LearningStore(engine._base_path, config, SemanticClient(engine._base_path, config)) as learning:
        learned = learning.context(query, cwd, max_tokens=max_tokens, delivered=False)
    prefix = learned["context"]
    remaining = max_tokens - count_tokens(prefix)
    if remaining < 10:
        return prefix
    result = await engine.recall(
        query=query,
        max_tokens=remaining,
        scope=scope,
        depth=depth,
        cwd=cwd,
    )

    # Budget the actual tool response, including labels and separators, not
    # just the stored content. A non-fitting item must not hide shorter ones.
    parts: list[str] = [prefix] if prefix else []
    for item in result.memories:
        candidate = f"[{item.scope}] {item.content}"
        if count_tokens("\n".join([*parts, candidate])) <= max_tokens:
            parts.append(candidate)
    if parts:
        return "\n".join(parts)
    empty = "No relevant memories found."
    return empty if count_tokens(empty) <= max_tokens else ""
