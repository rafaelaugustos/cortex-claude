from __future__ import annotations

from cortex_claude.core.engine import CortexEngine


async def handle_facts(
    engine: CortexEngine,
    topic: str,
    cwd: str,
    relation: str | None = None,
    scope: str | None = None,
    limit: int = 20,
) -> str:
    facts = await engine.get_facts(
        topic=topic,
        relation=relation,
        scope=scope,
        limit=limit,
        cwd=cwd,
    )

    if not facts:
        return f"No facts found for '{topic}'."

    lines = [f"Found {len(facts)} facts for '{topic}':"]
    for fact in facts:
        temporal = f" [{fact.temporal}]" if fact.temporal else ""
        lines.append(f"  {fact.subject} → {fact.relation} → {fact.object} (confidence: {fact.confidence:.1f}){temporal}")

    return "\n".join(lines)
