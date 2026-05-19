from __future__ import annotations

import asyncio

from cortex_claude.clustering import ClusteringConfig, ClusteringEngine
from cortex_claude.core.engine import CortexEngine
from cortex_claude.server.config import CortexConfig


async def handle_clusters(
    engine: CortexEngine,
    cwd: str,
    action: str = "list",
    scope: str | None = None,
    limit: int = 50,
) -> str:
    if action == "backfill":
        return await _handle_backfill(engine, cwd, scope)

    if action != "list":
        return f"unknown action: {action} (expected 'list' or 'backfill')"

    clusters = await engine.list_clusters(scope=scope, cwd=cwd)
    if not clusters:
        return "(no clusters yet — they form automatically as memories accumulate; run action='backfill' to seed from existing memories)"

    clusters.sort(key=lambda c: c["member_count"], reverse=True)
    clusters = clusters[:limit]

    lines = [
        f"{'Scope':<22} {'ID':>5} {'Members':>8}  Label",
        "-" * 80,
    ]
    for c in clusters:
        label = c["label"] or "(unlabeled)"
        lines.append(f"{c['scope']:<22} {c['id']:>5} {c['member_count']:>8}  {label}")

    return "\n".join(lines)


async def _handle_backfill(engine: CortexEngine, cwd: str, scope: str | None) -> str:
    if scope:
        scopes = [scope]
    else:
        scopes = engine._scope_manager.resolve(cwd) or ["global"]

    config = CortexConfig.load(engine._base_path)
    cluster_engine = ClusteringEngine(ClusteringConfig.from_dict(config.clustering))

    lines = ["Backfilling clusters..."]
    for s in scopes:
        await asyncio.to_thread(engine.reset_clusters, s)
        conn = engine.get_scope_connection(s)
        stats = await asyncio.to_thread(cluster_engine.cluster_scope, conn, s)
        lines.append(
            f"  {s}: assigned={stats.assigned}  new_clusters={stats.new_clusters}  "
            f"relabeled={stats.relabeled}"
        )

    lines.append("")
    lines.append("Top clusters after backfill:")
    for s in scopes:
        clusters = await engine.list_clusters(scope=s, cwd=cwd)
        clusters.sort(key=lambda c: c["member_count"], reverse=True)
        for c in clusters[:10]:
            label = c["label"] or "(unlabeled)"
            lines.append(f"  [{s}] id={c['id']:>4}  members={c['member_count']:>4}  {label}")

    return "\n".join(lines)
