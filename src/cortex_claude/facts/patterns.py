from __future__ import annotations

import re

from cortex_claude.facts.normalizer import normalize_entity, normalize_relation
from cortex_claude.models.fact import Fact

RELATION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "X is set to Y" / "X defaults to Y"
    (re.compile(r"(\w[\w\s-]+?)\s+(?:is set to|defaults? to|equals?)\s+(.+?)(?:\.|,|$)", re.I), "defaults_to"),
    # "rate limit: 1000 req/min"
    (re.compile(r"(rate[\s_-]?limit)\w*[:\s]+(\d+\s*[\w/]+)", re.I), "has_value"),
    # "port = 8080" / "port: 8080"
    (re.compile(r"(port)\s*[=:]\s*(\d+)", re.I), "has_value"),
    # "version = 3.13" / "version: 3.13"
    (re.compile(r"(version)\s*[=:]\s*([\d.]+)", re.I), "has_value"),
]

# "- X for/para Y" bullet patterns
BULLET_PATTERN = re.compile(
    r"^[\s]*[-*•]\s*(.+?)\s+(?:for|para|pra|→|->)\s+(.+?)$",
    re.MULTILINE | re.IGNORECASE,
)

# "- X + Y for/para Z" (tech combos)
BULLET_COMBO_PATTERN = re.compile(
    r"^[\s]*[-*•]\s*(.+?)$",
    re.MULTILINE,
)

# "Key: Value" on its own line or after newline
KV_PATTERN = re.compile(
    r"^[\s]*([A-Za-z][\w\s-]{1,30}):\s+([A-Za-z][\w\s,./()+&-]+?)$",
    re.MULTILINE,
)

# "X with Y" / "X using Y" / "X via Y"
WITH_PATTERN = re.compile(
    r"(\w[\w\s-]+?)\s+(?:with|using|via|com|usando)\s+([\w][\w\s-]+?)(?:\s+(?:for|para|pra)\s+([\w][\w\s-]+?))?(?:\.|,|$)",
    re.IGNORECASE,
)

# "X (Y)" parenthetical — X is associated with Y
PAREN_PATTERN = re.compile(
    r"(\w[\w\s-]+?)\s*\(([^)]+)\)",
)

# "X/Y" slash-separated tech (split into individual items)
SLASH_PATTERN = re.compile(
    r"\b([A-Z][\w.]*)/([A-Z][\w.]*)\b",
)

# Comma-separated list after "uses/usa/utiliza"
USES_LIST_PATTERN = re.compile(
    r"(?:uses?|usa|utiliza|utilizes?|exposes?|includes?|supports?)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)


def _split_list_items(text: str) -> list[str]:
    text = re.sub(r"\s+and\s+", ", ", text, flags=re.I)
    text = re.sub(r"\s+e\s+", ", ", text, flags=re.I)
    items = [item.strip() for item in text.split(",")]
    return [item for item in items if item and len(item) >= 2]


def _is_valid(subject: str, obj: str) -> bool:
    if len(subject) < 2 or len(obj) < 2:
        return False
    if len(subject) > 60 or len(obj) > 100:
        return False
    return True


def extract_facts_patterns(text: str) -> list[Fact]:
    facts: list[Fact] = []

    # Standard relation patterns
    for pattern, default_relation in RELATION_PATTERNS:
        for match in pattern.finditer(text):
            subject = match.group(1).strip()
            obj = match.group(2).strip()
            if _is_valid(subject, obj):
                facts.append(Fact(
                    subject=normalize_entity(subject),
                    relation=normalize_relation(default_relation),
                    object=normalize_entity(obj),
                    confidence=0.6,
                ))

    # Bullet: "- X for Y" / "- X para Y"
    for match in BULLET_PATTERN.finditer(text):
        tool = match.group(1).strip()
        purpose = match.group(2).strip()
        if _is_valid(tool, purpose):
            facts.append(Fact(
                subject=normalize_entity(tool),
                relation="used_for",
                object=normalize_entity(purpose),
                confidence=0.7,
            ))

    # Key: Value
    for match in KV_PATTERN.finditer(text):
        key = match.group(1).strip()
        value = match.group(2).strip()
        if _is_valid(key, value):
            # If value is a comma list, split it
            items = _split_list_items(value)
            if len(items) > 1:
                for item in items:
                    if len(item) >= 2:
                        facts.append(Fact(
                            subject=normalize_entity(key),
                            relation="includes",
                            object=normalize_entity(item),
                            confidence=0.65,
                        ))
            else:
                facts.append(Fact(
                    subject=normalize_entity(key),
                    relation="has_value",
                    object=normalize_entity(value),
                    confidence=0.6,
                ))

    # "X with Y (for Z)"
    for match in WITH_PATTERN.finditer(text):
        subject = match.group(1).strip()
        companion = match.group(2).strip()
        purpose = match.group(3)
        if _is_valid(subject, companion):
            facts.append(Fact(
                subject=normalize_entity(subject),
                relation="uses",
                object=normalize_entity(companion),
                confidence=0.7,
            ))
            if purpose and _is_valid(companion, purpose.strip()):
                facts.append(Fact(
                    subject=normalize_entity(companion),
                    relation="used_for",
                    object=normalize_entity(purpose.strip()),
                    confidence=0.65,
                ))

    # "X (Y)" parenthetical
    for match in PAREN_PATTERN.finditer(text):
        subject = match.group(1).strip()
        detail = match.group(2).strip()
        if _is_valid(subject, detail) and len(detail) < 50:
            facts.append(Fact(
                subject=normalize_entity(subject),
                relation="associated_with",
                object=normalize_entity(detail),
                confidence=0.6,
            ))

    # Slash-separated: "React/TypeScript" → two entities
    for match in SLASH_PATTERN.finditer(text):
        a = match.group(1).strip()
        b = match.group(2).strip()
        # Find context — what comes before?
        start = max(0, match.start() - 80)
        context = text[start:match.start()].strip()
        context_words = context.split()
        if context_words:
            parent = context_words[-1]
            if parent.endswith(":"):
                parent = parent[:-1]
            if len(parent) >= 2:
                for item in [a, b]:
                    facts.append(Fact(
                        subject=normalize_entity(parent),
                        relation="includes",
                        object=normalize_entity(item),
                        confidence=0.6,
                    ))

    # Comma lists after "uses/exposes/..."
    for match in USES_LIST_PATTERN.finditer(text):
        list_text = match.group(1).strip()
        items = _split_list_items(list_text)
        if len(items) >= 2:
            # Find subject before the verb
            verb_start = match.start()
            before = text[:verb_start].strip()
            subject_words = before.split()
            subject = subject_words[-1] if subject_words else ""
            # Walk back to find a real subject (skip "the", "a", etc.)
            for i in range(len(subject_words) - 1, -1, -1):
                candidate = subject_words[i].strip(".,;:")
                if candidate.lower() not in ("the", "a", "an", "o", "os", "as", ""):
                    subject = " ".join(subject_words[max(0, i-1):i+1]).strip(".,;: ")
                    break
            if len(subject) >= 2:
                for item in items:
                    if len(item) >= 2:
                        facts.append(Fact(
                            subject=normalize_entity(subject),
                            relation="uses",
                            object=normalize_entity(item),
                            confidence=0.65,
                        ))

    return facts
