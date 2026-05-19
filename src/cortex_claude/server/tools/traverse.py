from __future__ import annotations

from cortex_claude.core.engine import CortexEngine


async def handle_traverse(
    engine: CortexEngine,
    start: str,
    cwd: str,
    max_hops: int = 2,
    scope: str | None = None,
) -> str:
    facts = await engine.traverse_graph(
        start=start,
        max_hops=max_hops,
        scope=scope,
        cwd=cwd,
    )

    if not facts:
        if start.startswith("cluster:"):
            return (
                f"No connections found for {start}. "
                f"Check the cluster ID with cortex_clusters."
            )
        return f"No connections found from '{start}'."

    lines = [f"Graph traversal from '{start}' ({max_hops} hops, {len(facts)} connections):"]
    for fact in facts:
        lines.append(f"  {fact.subject} → {fact.relation} → {fact.object} ({fact.confidence:.1f})")

    return "\n".join(lines)
