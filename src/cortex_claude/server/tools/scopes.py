from __future__ import annotations

from cortex_claude.core.engine import CortexEngine


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


async def handle_scopes(
    engine: CortexEngine,
    action: str,
    cwd: str,
    name: str | None = None,
    path: str | None = None,
) -> str:
    result = await engine.manage_scopes(
        action=action,
        name=name,
        path=path,
        cwd=cwd,
    )

    if action == "list":
        scopes = result.get("scopes", [])
        if not scopes:
            return "No scopes found."
        lines = [f"{'Scope':<25} {'Memories':>10} {'Facts':>10} {'Size':>10}"]
        lines.append("-" * 60)
        for s in scopes:
            lines.append(
                f"{s['name']:<25} {s['memories']:>10} {s['facts']:>10} {_format_size(s['size_bytes']):>10}"
            )
        return "\n".join(lines)

    elif action == "info":
        return (
            f"Scope: {result.get('scope')}\n"
            f"Memories: {result.get('memories', 0)}\n"
            f"Facts: {result.get('facts', 0)}\n"
            f"Size: {_format_size(result.get('size_bytes', 0))}"
        )

    return f"{action}: {result.get('status', 'done')}"
