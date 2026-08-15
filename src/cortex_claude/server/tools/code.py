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

    # Optional "path:name" form to disambiguate when the same name is
    # defined in multiple files (e.g. "src/a.py:run" vs "src/b.py:run").
    # Falls back to plain-name lookup (matching every file) when there's
    # no ":" — same as before this disambiguation was added.
    want_path: str | None = None
    lookup_name = symbol
    if ":" in symbol:
        maybe_path, _, maybe_name = symbol.rpartition(":")
        if maybe_path and maybe_name:
            want_path, lookup_name = maybe_path, maybe_name

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
            (s, lookup_name),
        ).fetchall()

        if not defined_rows:
            continue

        # Group by defining file (object is "path:line") so calls/imports
        # from unrelated same-named symbols in other files aren't mixed
        # into one block. If `want_path` was given, only that file's
        # section is shown.
        by_file: dict[str, list[str]] = {}
        for (obj,) in defined_rows:
            file_path = obj.rsplit(":", 1)[0] if ":" in obj else obj
            by_file.setdefault(file_path, []).append(obj)

        if want_path is not None:
            by_file = {p: locs for p, locs in by_file.items() if p == want_path}
            if not by_file:
                continue

        found_any = True

        for file_path, locations in by_file.items():
            qualified = f"{file_path}:{lookup_name}"
            lines.append(f"[{s}] {lookup_name}  ({file_path})")
            for loc in locations:
                lines.append(f"  defined_in: {loc}")

            lang_rows = conn.execute(
                "SELECT DISTINCT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'in_language'",
                (s, lookup_name),
            ).fetchall()
            if lang_rows:
                langs = ", ".join(r[0] for r in lang_rows)
                lines.append(f"  language: {langs}")

            calls = conn.execute(
                "SELECT DISTINCT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'calls' LIMIT 20",
                (s, lookup_name),
            ).fetchall()
            if calls:
                lines.append(f"  calls: {', '.join(r[0] for r in calls)}")

            calls_from = conn.execute(
                "SELECT DISTINCT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'calls_from' LIMIT 20",
                (s, qualified),
            ).fetchall()
            if calls_from:
                resolved = ", ".join(r[0] for r in calls_from)
                lines.append(f"  calls (resolved to import): {resolved}")

            callers = conn.execute(
                "SELECT DISTINCT subject FROM facts WHERE scope = ? AND relation = 'calls' AND object = ? LIMIT 20",
                (s, lookup_name),
            ).fetchall()
            if callers:
                lines.append(f"  called_by: {', '.join(r[0] for r in callers)}")

            extends = conn.execute(
                "SELECT DISTINCT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'extends'",
                (s, lookup_name),
            ).fetchall()
            if extends:
                lines.append(f"  extends: {', '.join(r[0] for r in extends)}")

            imports = conn.execute(
                "SELECT DISTINCT object FROM facts WHERE scope = ? AND subject = ? AND relation = 'imports' LIMIT 20",
                (s, lookup_name),
            ).fetchall()
            if imports:
                lines.append(f"  imports: {', '.join(r[0] for r in imports)}")

            mentions = conn.execute(
                "SELECT DISTINCT subject FROM facts WHERE scope = ? AND relation = 'mentions' AND object = ? LIMIT 10",
                (s, lookup_name),
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
    max_files: int | None = None,
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

    truncated = False
    if max_files is not None and len(files) > max_files:
        files = files[:max_files]
        truncated = True

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
        # Re-indexing an edited file must not accumulate stale facts for
        # symbols that were removed or renamed since the last index.
        repo.delete_by_source_file(conn, write_scope, str(f))
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
    if truncated:
        lines.append(f"  note:    stopped at max_files={max_files}, more files were not indexed")
    return "\n".join(lines)
