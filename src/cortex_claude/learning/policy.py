"""Cheap applicability and freshness checks; no model or shell execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cortex_claude.core.privacy import strip_private
from cortex_claude.learning.extraction import normalize, terms


def clean_conditions(value: dict | None) -> dict[str, list[str]]:
    if not isinstance(value or {}, dict) or set(value or {}) - {"all", "any", "none"}:
        raise ValueError("conditions accepts all/any/none lists of task cues")
    result = {}
    for key, cues in (value or {}).items():
        if not isinstance(cues, list) or len(cues) > 8 or any(not isinstance(c, str) for c in cues):
            raise ValueError("Each condition must be a list of at most 8 strings")
        cleaned = sorted({normalize(strip_private(c)) for c in cues})
        if any(not c or len(c) > 120 for c in cleaned):
            raise ValueError("Condition cues must contain 1–120 non-private characters")
        if cleaned:
            result[key] = cleaned
    return result


def condition_key(conditions: dict) -> str:
    return json.dumps(conditions, sort_keys=True, separators=(",", ":")) if conditions else ""


def applies(conditions: dict, query: str) -> bool:
    words = terms(query)
    def matches(cue: str) -> bool:
        wanted = terms(cue)
        return bool(wanted) and wanted <= words
    return (all(matches(c) for c in conditions.get("all", []))
            and (not conditions.get("any") or any(matches(c) for c in conditions["any"]))
            and not any(matches(c) for c in conditions.get("none", [])))


def describe_conditions(conditions: dict) -> str:
    labels = {"all": "when", "any": "when any of", "none": "except"}
    return "; ".join(f"{labels[k]} {', '.join(v)}" for k, v in conditions.items() if v)


def fingerprint(path: Path) -> str:
    # Bounded I/O, including symlinks and files changing while being read.
    with path.open("rb") as stream:
        data = stream.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("Dependency files must be at most 2 MB")
    return hashlib.sha256(data).hexdigest()


def snapshot(origin: str, paths: list[str]) -> dict[str, str]:
    if len(paths) > 20:
        raise ValueError("At most 20 dependency files per lesson")
    root = Path(origin).resolve()
    result = {}
    for value in paths:
        if not isinstance(value, str) or strip_private(value) != value:
            raise ValueError("Invalid dependency path")
        path = (root / value).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Dependency must be a file inside the current repository")
        result[str(path.relative_to(root))] = fingerprint(path)
    return result


def changed(origin: str, dependencies: dict[str, str]) -> bool:
    try:
        return bool(dependencies) and snapshot(origin, list(dependencies)) != dependencies
    except (OSError, ValueError):
        return True
