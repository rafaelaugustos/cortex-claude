from __future__ import annotations

import re


def normalize_entity(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(the|a|an)\s+", "", text)
    return text


def normalize_relation(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "_", text)
    return text
