from __future__ import annotations

import re
import sqlite3

from cortex_claude.code.extractor import Symbol
from cortex_claude.models.fact import Fact


CODE_FACT_CONFIDENCE = 0.95
MENTION_CONFIDENCE = 0.7

# Minimum identifier length is 4 (not 3): short, extremely common names like
# "get"/"run"/"set" are very likely to appear in memory text without meaning
# "this memory is about that function" — they're the biggest source of false
# `mentions` facts. Combined with _MENTION_STOPLIST below for common names
# that survive the length cut.
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")

_MENTION_STOPLIST = {
    "init", "main", "test", "self", "this", "data", "value", "index", "type", "name",
}


def known_symbol_names(conn: sqlite3.Connection, scope: str) -> set[str]:
    """Return the set of symbol names indexed in this scope. Uses 'defined_in'
    relation as the canonical marker that a subject is a code symbol."""
    rows = conn.execute(
        "SELECT DISTINCT subject FROM facts WHERE scope = ? AND relation = 'defined_in'",
        (scope,),
    ).fetchall()
    return {r[0] for r in rows if r[0]}


def mention_facts(
    memory_id: str,
    content: str,
    known_symbols: set[str],
    scope: str,
) -> list[Fact]:
    """Find symbol names mentioned in memory content and emit
    `memory:<id> → mentions → <symbol>` facts.

    This is best-effort textual matching, not scope-aware analysis: it has
    no notion of imports or lexical scope, so a memory mentioning a common
    word can link to every same-named symbol in the project. `_IDENT_RE`'s
    length cutoff and `_MENTION_STOPLIST` reduce the worst false positives
    (short, generic names) but do not eliminate them.
    """
    if not known_symbols or not content:
        return []

    tokens = set(_IDENT_RE.findall(content))
    matched = (tokens & known_symbols) - _MENTION_STOPLIST
    if not matched:
        return []

    return [
        Fact(
            subject=f"memory:{memory_id}",
            relation="mentions",
            object=sym,
            confidence=MENTION_CONFIDENCE,
            source_memory_id=memory_id,
            scope=scope,
        )
        for sym in matched
    ]


def symbols_to_facts(symbols: list[Symbol]) -> list[Fact]:
    """Convert extracted symbols into knowledge-graph facts.

    Vocabulary:
      - subject → defined_in → path:line   (one per symbol)
      - subject → in_language → lang       (one per symbol)
      - subject → calls → callee           (one per call site)
      - subject → extends → parent_class
      - subject → imports → module_path

    `calls`/`extends` resolution is purely textual (same-name matching
    within the parsed file), not scope- or import-aware — two same-named
    functions in different files/scopes will share the same graph node.
    """
    facts: list[Fact] = []
    seen: set[tuple[str, str, str]] = set()

    def add(subject: str, relation: str, obj: str) -> None:
        key = (subject.lower(), relation, obj.lower())
        if key in seen:
            return
        seen.add(key)
        facts.append(
            Fact(
                subject=subject,
                relation=relation,
                object=obj,
                confidence=CODE_FACT_CONFIDENCE,
                source_memory_id=None,
            )
        )

    for sym in symbols:
        location = f"{sym.path}:{sym.line}"
        add(sym.name, "defined_in", location)
        add(sym.name, "in_language", sym.language)

        for callee in sym.calls:
            add(sym.name, "calls", callee)

        for parent in sym.extends:
            add(sym.name, "extends", parent)

        for module in sym.imports:
            add(sym.name, "imports", module)

    return facts
