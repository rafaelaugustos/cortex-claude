from __future__ import annotations

from cortex_claude.facts.patterns import extract_facts_patterns
from cortex_claude.facts.spacy_extract import extract_facts_spacy
from cortex_claude.models.fact import Fact


def _deduplicate_facts(facts: list[Fact]) -> list[Fact]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[Fact] = []

    for fact in facts:
        key = (fact.subject, fact.relation, fact.object)
        if key not in seen:
            seen.add(key)
            unique.append(fact)

    return unique


def extract_facts(text: str, min_confidence: float = 0.5) -> list[Fact]:
    facts: list[Fact] = []

    facts.extend(extract_facts_spacy(text))
    facts.extend(extract_facts_patterns(text))

    facts = _deduplicate_facts(facts)
    facts = [f for f in facts if f.confidence >= min_confidence]
    facts.sort(key=lambda f: f.confidence, reverse=True)

    return facts
