from __future__ import annotations

import re
from datetime import datetime

TEMPORAL_PATTERNS = [
    # "in April 2024", "em abril de 2024"
    re.compile(r"\b(?:in|em|on|since|desde|until|até)\s+((?:january|february|march|april|may|june|july|august|september|october|november|december|janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s*(?:de\s*)?\d{4})\b", re.I),
    # "2024-04-15", "15/04/2024"
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{2}/\d{2}/\d{4})\b"),
    # "Q1 2024", "Q3 2025"
    re.compile(r"\b(Q[1-4]\s*\d{4})\b", re.I),
    # "last week", "yesterday", "today", "recently"
    re.compile(r"\b(yesterday|today|last\s+(?:week|month|year)|this\s+(?:week|month|year)|recently|ontem|hoje|semana\s+passada|mês\s+passado)\b", re.I),
    # "2 days ago", "3 weeks ago", "há 2 dias"
    re.compile(r"\b(\d+\s+(?:days?|weeks?|months?|years?|dias?|semanas?|meses|anos?)\s+ago)\b", re.I),
    re.compile(r"\b(há\s+\d+\s+(?:dias?|semanas?|meses|anos?))\b", re.I),
    # "since v2", "after the migration", "before release"
    re.compile(r"\b(since\s+v[\d.]+|desde\s+(?:a\s+)?v[\d.]+)\b", re.I),
    # "April", "March" standalone month (current year implied)
    re.compile(r"\b(?:in|em)\s+(january|february|march|april|may|june|july|august|september|october|november|december|janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b", re.I),
]

TEMPORAL_KEYWORDS = [
    "changed", "migrated", "updated", "switched", "moved", "deprecated",
    "removed", "added", "started", "stopped", "began", "ended",
    "mudou", "migrou", "atualizou", "trocou", "removeu", "adicionou",
    "was", "were", "used to", "previously", "formerly", "now",
    "antes", "agora", "anteriormente",
]


def extract_temporal(text: str) -> str | None:
    for pattern in TEMPORAL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()

    text_lower = text.lower()
    for kw in TEMPORAL_KEYWORDS:
        if kw in text_lower:
            now = datetime.now()
            return f"~{now.strftime('%Y-%m')}"

    return None


def attach_temporal_to_facts(text: str, facts: list) -> None:
    temporal = extract_temporal(text)
    if not temporal:
        return

    for fact in facts:
        if fact.temporal is None:
            fact.temporal = temporal
