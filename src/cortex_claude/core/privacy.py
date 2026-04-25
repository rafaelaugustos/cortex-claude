from __future__ import annotations

import re

PRIVATE_PATTERN = re.compile(r"<private>.*?</private>", re.DOTALL | re.IGNORECASE)
PRIVATE_BLOCK_PATTERN = re.compile(r"<private\s*/?>", re.IGNORECASE)


def strip_private(text: str) -> str:
    text = PRIVATE_PATTERN.sub("", text)
    text = PRIVATE_BLOCK_PATTERN.sub("", text)
    return text.strip()


def contains_private(text: str) -> bool:
    return bool(PRIVATE_PATTERN.search(text) or PRIVATE_BLOCK_PATTERN.search(text))


def is_fully_private(text: str) -> bool:
    stripped = strip_private(text)
    return len(stripped) == 0
