from __future__ import annotations

from cortex_claude.core.engine import CortexEngine


async def handle_forget(
    engine: CortexEngine,
    cwd: str,
    query: str | None = None,
    memory_id: str | None = None,
    scope: str | None = None,
    dry_run: bool = True,
) -> str:
    result = await engine.forget(
        query=query,
        memory_id=memory_id,
        scope=scope,
        dry_run=dry_run,
        cwd=cwd,
    )

    if not result.deleted:
        return "No matching memories found to delete."

    action = "Would delete" if result.dry_run else "Deleted"
    lines = [f"{action} {len(result.deleted)} memory(s) from scope '{result.scope}':"]
    for mid in result.deleted:
        lines.append(f"  - {mid}")

    if result.dry_run:
        lines.append("\nThis is a dry run. Set dry_run=false to actually delete.")

    return "\n".join(lines)
