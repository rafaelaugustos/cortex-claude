from __future__ import annotations

from cortex_claude.core.engine import CortexEngine
from cortex_claude.learning.store import LearningStore


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


async def handle_status(
    engine: CortexEngine,
    cwd: str,
    scope: str | None = None,
) -> str:
    result = await engine.status(scope=scope, cwd=cwd)
    with LearningStore(engine._base_path) as learning:
        learned = learning.stats()

    lines = [
        "=== Cortex Claude Status ===",
        f"Total memories: {result.total_memories}",
        f"Total facts: {result.total_facts}",
        f"Total storage: {_format_size(result.total_size_bytes)}",
        f"Shared learned preferences/lessons: {learned['states'].get('active', 0)}",
        f"Awaiting evidence: {learned['states'].get('candidate', 0)}",
        f"Context tokens injected (estimate): {learned['injected_tokens']}",
        f"Repeated content tokens avoided (estimate): {learned['repeat_tokens_avoided']}",
        "",
        f"{'Scope':<25} {'Memories':>10} {'Facts':>10} {'Size':>10}",
        "-" * 60,
    ]

    for s in result.scopes:
        lines.append(
            f"{s['name']:<25} {s['memories']:>10} {s['facts']:>10} {_format_size(s['size_bytes']):>10}"
        )

    return "\n".join(lines)
