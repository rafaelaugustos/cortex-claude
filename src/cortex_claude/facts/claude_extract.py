from __future__ import annotations

import json
import os

from cortex_claude.facts.normalizer import normalize_entity, normalize_relation
from cortex_claude.models.fact import Fact

EXTRACTION_PROMPT = """Extract structured facts from the following text as subject-relation-object triplets.

Rules:
- Each fact must be a (subject, relation, object) triple
- Normalize entities to lowercase
- Use simple verb forms for relations (use, store, deploy, run, etc.)
- Extract ALL meaningful facts, including implicit ones
- Return valid JSON array

Text:
{text}

Return ONLY a JSON array of objects with keys "subject", "relation", "object". No markdown, no explanation.
Example: [{"subject": "auth service", "relation": "uses", "object": "jwt"}]"""


def extract_facts_claude(text: str) -> list[Fact]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []

    try:
        import anthropic
    except ImportError:
        return []

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": EXTRACTION_PROMPT.format(text=text)},
        ],
    )

    raw = response.content[0].text.strip()

    # Handle potential markdown wrapping
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    facts: list[Fact] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject", "").strip()
        relation = item.get("relation", "").strip()
        obj = item.get("object", "").strip()

        if not subject or not relation or not obj:
            continue

        facts.append(Fact(
            subject=normalize_entity(subject),
            relation=normalize_relation(relation),
            object=normalize_entity(obj),
            confidence=0.9,
        ))

    return facts
