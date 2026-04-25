from __future__ import annotations

from cortex_claude.facts.normalizer import entities_match
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


def _canonicalize_entities(facts: list[Fact]) -> list[Fact]:
    entity_groups: dict[str, str] = {}

    all_entities: list[str] = []
    for f in facts:
        if f.subject not in all_entities:
            all_entities.append(f.subject)
        if f.object not in all_entities:
            all_entities.append(f.object)

    for entity in all_entities:
        if entity in entity_groups:
            continue
        for other in all_entities:
            if other == entity or other in entity_groups:
                continue
            if entities_match(entity, other):
                canonical = entity if len(entity) >= len(other) else other
                entity_groups[entity] = canonical
                entity_groups[other] = canonical
                break

    if not entity_groups:
        return facts

    for fact in facts:
        if fact.subject in entity_groups:
            fact.subject = entity_groups[fact.subject]
        if fact.object in entity_groups:
            fact.object = entity_groups[fact.object]

    return facts


def _clean_facts(facts: list[Fact], min_confidence: float) -> list[Fact]:
    facts = _deduplicate_facts(facts)
    facts = _canonicalize_entities(facts)
    facts = _deduplicate_facts(facts)
    facts = [f for f in facts if f.confidence >= min_confidence and f.subject != f.object]
    facts.sort(key=lambda f: f.confidence, reverse=True)
    return facts


def extract_facts(
    text: str,
    min_confidence: float = 0.5,
    claude_fallback: bool = False,
    claude_confidence_threshold: float = 0.5,
) -> list[Fact]:
    if not text or not text.strip():
        return []

    facts: list[Fact] = []

    facts.extend(extract_facts_spacy(text))
    facts.extend(extract_facts_patterns(text))
    facts = _clean_facts(facts, min_confidence)

    if claude_fallback and _should_use_claude(facts, claude_confidence_threshold):
        from cortex_claude.facts.claude_extract import extract_facts_claude
        claude_facts = extract_facts_claude(text)
        facts.extend(claude_facts)
        facts = _clean_facts(facts, min_confidence)

    return facts


def _should_use_claude(facts: list[Fact], threshold: float) -> bool:
    if len(facts) < 2:
        return True
    high_confidence = [f for f in facts if f.confidence > threshold]
    return len(high_confidence) < 2
