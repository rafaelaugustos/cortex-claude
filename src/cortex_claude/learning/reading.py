"""Bounded file reads with session-local, content-verified deltas."""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from cortex_claude.embeddings.tokenizer import count_tokens

if TYPE_CHECKING:
    from cortex_claude.learning.store import LearningStore


def redact_lines(text: str) -> str:
    # Preserve source line numbers while preventing private spans from
    # entering the cache, hash, full response or a later deletion diff.
    return re.sub(r"<private>.*?(?:</private>|$)", lambda m: "[private]" + "\n" * m[0].count("\n"), text, flags=re.S | re.I)


def read_file(store: LearningStore, cwd: str, path: str, session_id: str | None = None,
              start_line: int = 1, end_line: int | None = None,
              max_tokens: int = 800, mode: str = "auto") -> str:
    from cortex_claude.learning.store import context_origin
    if mode not in {"auto", "full"} or start_line < 1 or (end_line is not None and end_line < start_line):
        raise ValueError("Invalid mode or line range")
    if not 80 <= max_tokens <= 4000:
        raise ValueError("max_tokens must be between 80 and 4000")
    origin = context_origin(cwd)
    root = Path(origin).resolve()
    target = (Path(cwd) / path).resolve()
    if not target.is_relative_to(root) or not target.is_file() or ".git" in target.relative_to(root).parts:
        raise ValueError("Read a regular source file inside the current repository")
    with target.open("rb") as stream:
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000 or b"\x00" in raw:
        raise ValueError("Only text files of at most 2 MB are supported")
    try:
        lines = redact_lines(raw.decode("utf-8")).splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("The file must use UTF-8") from error
    relative = str(target.relative_to(root))
    stop = min(end_line if end_line is not None else start_line + 199, len(lines))
    if start_line > max(len(lines), 1):
        raise ValueError("start_line is past the end of the file")
    range_key = f"{start_line}:{end_line or 'auto'}:{max_tokens}"
    sid = session_id or store.delivery_session(cwd)
    if not store.config.enabled:
        mode, sid = "full", None
    if sid:
        sid = store.session(sid, cwd)
    # An ambiguous caller gets a full read. A shared/manual cache would leak
    # another conversation's delivery state and yield an unusable diff.
    previous = store.conn.execute("SELECT * FROM file_reads WHERE session_id=? AND origin=? AND path=? AND range_key=?", (sid, origin, relative, range_key)).fetchone() if sid and mode == "auto" else None
    selected: list[str] = []
    result = {}
    def full_result(chosen: list[str]) -> dict:
        text = "\n".join(chosen)
        return {"path": relative, "mode": "full", "hash": hashlib.sha256(text.encode()).hexdigest()[:16],
            "start_line": start_line, "end_line": start_line + len(chosen) - 1,
            "more": start_line + len(chosen) - 1 < len(lines),
            "content": "\n".join(f"{start_line + i}: {line}" for i, line in enumerate(chosen))}
    for line in lines[start_line - 1:stop]:
        candidate = full_result([*selected, line])
        if count_tokens(json.dumps(candidate, ensure_ascii=False)) > max_tokens:
            break
        selected.append(line)
        result = candidate
    if not selected and lines:
        raise ValueError("The first requested line exceeds the budget; increase max_tokens")
    result = result or full_result([])
    full_tokens = count_tokens(json.dumps(result, ensure_ascii=False))
    content = "\n".join(selected)
    if previous and previous["digest"] == result["hash"]:
        result = {k: v for k, v in result.items() if k != "content"}
        result["mode"] = "unchanged"
    elif previous:
        diff = "\n".join(difflib.unified_diff(previous["content"].splitlines(), selected, fromfile=f"{relative}@{previous['digest']}", tofile=f"{relative}@{result['hash']}", lineterm=""))
        delta = {**result, "mode": "diff", "base_hash": previous["digest"], "content": diff}
        if count_tokens(json.dumps(delta, ensure_ascii=False)) < full_tokens:
            result = delta
    rendered = json.dumps(result, ensure_ascii=False)
    emitted = count_tokens(rendered)
    if emitted > max_tokens:
        raise ValueError("The response metadata exceeds the budget; increase max_tokens")
    if sid:
        with store.conn:
            store.conn.execute("INSERT OR REPLACE INTO file_reads VALUES (?,?,?,?,?,?,?,?,?)", (sid, origin, relative, range_key, result["hash"], content, start_line, start_line + len(selected) - 1, time.time()))
            store.conn.execute("INSERT OR IGNORE INTO read_metrics(session_id) VALUES (?)", (sid,))
            field = {"full": "full_reads", "diff": "delta_reads", "unchanged": "unchanged_reads"}[result["mode"]]
            store.conn.execute(f"UPDATE read_metrics SET {field}={field}+1,emitted_tokens=emitted_tokens+?,avoided_tokens=avoided_tokens+? WHERE session_id=?", (emitted, max(0, full_tokens - emitted), sid))
    return rendered
