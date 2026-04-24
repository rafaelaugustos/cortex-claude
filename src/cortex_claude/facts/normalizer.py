from __future__ import annotations

import re
from difflib import SequenceMatcher

STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
              "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da",
              "dos", "das", "em", "no", "na", "nos", "nas", "por", "pelo", "pela"}

CANONICAL_ALIASES: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "pg": "postgresql",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "k8s": "kubernetes",
    "react.js": "react",
    "reactjs": "react",
    "next.js": "nextjs",
    "node.js": "nodejs",
    "vue.js": "vue",
}


def normalize_entity(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)

    words = text.split()
    words = [w for w in words if w not in STOP_WORDS]
    text = " ".join(words) if words else text

    if text in CANONICAL_ALIASES:
        text = CANONICAL_ALIASES[text]

    text = re.sub(r"[\s_-]+", " ", text).strip()
    return text


def normalize_relation(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "_", text)
    return text


def entities_match(a: str, b: str, threshold: float = 0.75) -> bool:
    if a == b:
        return True

    na = normalize_entity(a)
    nb = normalize_entity(b)

    if na == nb:
        return True

    if na in nb or nb in na:
        return True

    ratio = SequenceMatcher(None, na, nb).ratio()
    return ratio >= threshold


def find_canonical(entity: str, existing: list[str], threshold: float = 0.75) -> str | None:
    normalized = normalize_entity(entity)
    for candidate in existing:
        if entities_match(normalized, candidate, threshold):
            return candidate
    return None
