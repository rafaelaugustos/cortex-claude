from __future__ import annotations

from cortex_claude.core.engine import CortexEngine


async def handle_save(
    engine: CortexEngine,
    content: str,
    cwd: str,
    tags: list[str] | None = None,
    scope: str | None = None,
) -> str:
    result = await engine.save(
        content=content,
        tags=tags,
        scope=scope,
        cwd=cwd,
    )
    return (
        f"Saved memory {result.memory_id} "
        f"to scope '{result.scope}' "
        f"({result.tokens_stored} tokens)"
    )
