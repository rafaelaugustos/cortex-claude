from __future__ import annotations

import re

_TAG_PATTERN = re.compile(r"<(/?)private(\s*/)?>", re.IGNORECASE)


def strip_private(text: str) -> str:
    """Remove all <private>...</private> spans, including malformed/nested
    ones. Uses depth counting rather than a non-greedy regex: a non-greedy
    `<private>.*?</private>` closes at the *first* </private> it sees, so
    `<private>A<private>B</private>` would leak `B</private>` as saved
    content — a silent privacy leak. Depth counting treats everything from
    the first <private> up to the </private> that closes it at the same
    level as private, which is the safe-by-default behavior (over-redacting
    is acceptable; leaking is the bug we're fixing). A self-closing
    `<private/>` is a no-op marker (no span to redact), not an opening tag.
    """
    out: list[str] = []
    depth = 0
    pos = 0
    for match in _TAG_PATTERN.finditer(text):
        is_close = bool(match.group(1))
        is_self_closing = bool(match.group(2))
        if is_self_closing:
            if depth == 0:
                out.append(text[pos:match.start()])
                pos = match.end()
            continue
        if depth == 0:
            out.append(text[pos:match.start()])
        if is_close:
            depth = max(0, depth - 1)
        else:
            depth += 1
        pos = match.end()
    if depth == 0:
        out.append(text[pos:])
    return "".join(out).strip()


def contains_private(text: str) -> bool:
    return bool(_TAG_PATTERN.search(text))


def is_fully_private(text: str) -> bool:
    stripped = strip_private(text)
    return len(stripped) == 0
