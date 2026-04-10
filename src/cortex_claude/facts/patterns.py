from __future__ import annotations

import re

from cortex_claude.facts.normalizer import normalize_entity, normalize_relation
from cortex_claude.models.fact import Fact

PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(\w[\w\s-]+?)\s+(?:is set to|defaults? to|equals?)\s+(.+?)(?:\.|,|$)", re.I), "defaults_to"),
    (re.compile(r"([\w\s-]+?):\s+(.+?)(?:\.|,|$)", re.M), "has_value"),
    (re.compile(r"(rate[\s_-]?limit)\w*[:\s]+(\d+\s*\w+)", re.I), "has_value"),
    (re.compile(r"(port)\s*[=:]\s*(\d+)", re.I), "has_value"),
    (re.compile(r"(version)\s*[=:]\s*([\d.]+)", re.I), "has_value"),
]


def extract_facts_patterns(text: str) -> list[Fact]:
    facts: list[Fact] = []

    for pattern, default_relation in PATTERNS:
        for match in pattern.finditer(text):
            subject = match.group(1).strip()
            obj = match.group(2).strip()

            if len(subject) < 2 or len(obj) < 2:
                continue
            if len(subject) > 50 or len(obj) > 100:
                continue

            facts.append(Fact(
                subject=normalize_entity(subject),
                relation=normalize_relation(default_relation),
                object=normalize_entity(obj),
                confidence=0.6,
            ))

    return facts
