from __future__ import annotations

from cortex_claude.core.engine import CortexEngine


async def handle_recall(
    engine: CortexEngine,
    query: str,
    cwd: str,
    max_tokens: int = 200,
    scope: str | None = None,
) -> str:
    result = await engine.recall(
        query=query,
        max_tokens=max_tokens,
        scope=scope,
        cwd=cwd,
    )

    if not result.memories:
        return "No relevant memories found."

    parts: list[str] = []
    for item in result.memories:
        tags_str = f" [{', '.join(item.tags)}]" if item.tags else ""
        parts.append(
            f"[{item.scope}] (score: {item.score:.2f}){tags_str}\n{item.content}"
        )

    header = f"Found {len(result.memories)} memories ({result.total_tokens} tokens):\n"
    return header + "\n---\n".join(parts)
