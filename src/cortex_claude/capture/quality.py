"""Identify execution transcripts without rejecting documented development commands."""
from __future__ import annotations

import json
import re

_DUMP = re.compile(r"^(?:command:|bash:|read file:|file search:|created file:|edited\s+[/~.]|(?:read|edit|write|grep|glob|toolsearch|taskcreate|taskupdate|tasklist|structuredoutput):)", re.I)


def execution_dump(content: str, tags: list[str] | str) -> bool:
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (ValueError, TypeError):
            return False
    return isinstance(tags, list) and "auto-capture" in tags and bool(_DUMP.match(content.lstrip()))
