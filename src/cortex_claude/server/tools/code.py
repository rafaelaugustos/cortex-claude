from __future__ import annotations

import asyncio
from pathlib import Path

from cortex_claude.code import EXTENSION_TO_LANGUAGE, extract_symbols, is_supported_path
from cortex_claude.code.facts import symbols_to_facts
from cortex_claude.core.engine import CortexEngine
from cortex_claude.storage import FactRepository


async def handle_code(
    engine: CortexEngine,
    cwd: str,
    symbol: str,
    scope: str | None = None,
) -> str:
    if not symbol:
        return "symbol required"

    scopes = [scope] if scope else engine._scope_manager.resolve(cwd)

    found_any = False
    lines: list[str] = []

    for s in scopes:
        try:
            conn = engine.get_scope_connection(s)
        except Exception:
            continue

        defined_rows = conn.execute(
            "SELECT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'defined_in'",
            (s, symbol),
        ).fetchall()

        if not defined_rows:
            continue

        found_any = True
        lines.append(f"[{s}] {symbol}")
        for r in defined_rows:
            lines.append(f"  defined_in: {r[0]}")

        lang_rows = conn.execute(
            "SELECT DISTINCT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'in_language'",
            (s, symbol),
        ).fetchall()
        if lang_rows:
            langs = ", ".join(r[0] for r in lang_rows)
            lines.append(f"  language: {langs}")

        calls = conn.execute(
            "SELECT DISTINCT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'calls' LIMIT 20",
            (s, symbol),
        ).fetchall()
        if calls:
            lines.append(f"  calls: {', '.join(r[0] for r in calls)}")

        callers = conn.execute(
            "SELECT DISTINCT subject FROM facts WHERE scope = ? AND relation = 'calls' AND object = ? LIMIT 20",
            (s, symbol),
        ).fetchall()
        if callers:
            lines.append(f"  called_by: {', '.join(r[0] for r in callers)}")

        extends = conn.execute(
            "SELECT DISTINCT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'extends'",
            (s, symbol),
        ).fetchall()
        if extends:
            lines.append(f"  extends: {', '.join(r[0] for r in extends)}")

        imports = conn.execute(
            "SELECT DISTINCT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'imports' LIMIT 20",
            (s, symbol),
        ).fetchall()
        if imports:
            lines.append(f"  imports: {', '.join(r[0] for r in imports)}")

        mentions = conn.execute(
            "SELECT DISTINCT subject FROM facts WHERE scope = ? AND relation = 'mentions' AND object = ? LIMIT 10",
            (s, symbol),
        ).fetchall()
        if mentions:
            ids = ", ".join(r[0].replace("memory:", "")[:8] for r in mentions[:5])
            lines.append(f"  mentioned_in_memories: {len(mentions)} (ids: {ids}...)")

        lines.append("")

    if not found_any:
        return f"Symbol '{symbol}' not found in code graph. Index files first with cortex_index_code."

    return "\n".join(lines).rstrip()


_SKIP_DIRS = {"node_modules", "__pycache__", "dist", "build", ".venv", "venv", "target", ".git"}


async def handle_index_code(
    engine: CortexEngine,
    cwd: str,
    path: str,
    scope: str | None = None,
    recursive: bool = True,
) -> str:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return f"path not found: {target}"

    if target.is_file():
        files = [target] if is_supported_path(target) else []
    else:
        files = []
        glob_fn = target.rglob if recursive else target.glob
        for ext in EXTENSION_TO_LANGUAGE:
            files.extend(glob_fn(f"*{ext}"))
        files = [
            f for f in files
            if not any(part.startswith(".") or part in _SKIP_DIRS for part in f.parts)
        ]

    if not files:
        return f"no supported code files found at {target}"

    write_scope = scope or engine._scope_manager.get_write_scope(cwd)
    conn = engine.get_scope_connection(write_scope)
    repo = FactRepository()

    total_symbols = 0
    total_facts = 0
    indexed_files = 0
    errors = 0

    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            errors += 1
            continue

        try:
            symbols = await asyncio.to_thread(extract_symbols, str(f), content)
        except Exception:
            errors += 1
            continue

        if not symbols:
            continue

        facts = symbols_to_facts(symbols)
        if not facts:
            continue

        for fact in facts:
            fact.scope = write_scope
        repo.save_batch(conn, facts)

        total_symbols += len(symbols)
        total_facts += len(facts)
        indexed_files += 1

    lines = [
        f"Indexed {indexed_files} files into scope '{write_scope}'",
        f"  symbols: {total_symbols}",
        f"  facts:   {total_facts}",
    ]
    if errors:
        lines.append(f"  errors:  {errors}")
    return "\n".join(lines)
