"""Provider token counters and matched task evaluations, never billing guesses."""
from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path

COUNTERS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")


def _count(value) -> int:
    return value if type(value) is int and value >= 0 else 0


def ingest_transcript(conn: sqlite3.Connection, session_id: str, path: Path) -> dict:
    if path.suffix != ".jsonl" or not path.is_file():
        return {"status": "unavailable"}
    info = path.stat()
    file_id = f"{info.st_dev}:{info.st_ino}"
    previous = conn.execute("SELECT * FROM transcript_offsets WHERE session_id=? AND path=?", (session_id, str(path))).fetchone()
    start = previous["offset"] if previous and previous["file_id"] == file_id and previous["offset"] <= info.st_size else 0
    skipping = bool(previous and start and previous["skipping"])
    processed, consumed = 0, 0
    with path.open("rb") as stream, conn:
        stream.seek(start)
        while consumed < 8_000_000:
            position = stream.tell()
            line = stream.readline(2_000_001)
            if not line:
                break
            consumed += len(line)
            if skipping:
                skipping = not line.endswith(b"\n")
                continue
            if not line.endswith(b"\n"):
                if len(line) > 2_000_000:
                    skipping = True
                    continue
                stream.seek(position)  # Concurrent writer: retry next Stop.
                break
            try:
                data = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(data, dict) or data.get("type") != "assistant":
                continue
            if data.get("sessionId", session_id) not in {session_id, session_id.removeprefix('claude:')}:
                continue
            message = data.get("message") or {}
            if not isinstance(message, dict):
                continue
            usage, message_id = message.get("usage"), message.get("id")
            if not isinstance(usage, dict) or not isinstance(message_id, str):
                continue
            values = [_count(usage.get(k)) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")]
            # Streaming updates repeat a message's cumulative usage. MAX per
            # provider message ID makes repeated Stop hooks and replay harmless.
            conn.execute(
                "INSERT INTO usage_messages VALUES (?,?,?,?,?,?,?) ON CONFLICT(session_id,message_id) DO UPDATE SET "
                "input_tokens=MAX(input_tokens,excluded.input_tokens),output_tokens=MAX(output_tokens,excluded.output_tokens),"
                "cache_read_tokens=MAX(cache_read_tokens,excluded.cache_read_tokens),cache_creation_tokens=MAX(cache_creation_tokens,excluded.cache_creation_tokens)",
                (session_id, message_id, str(message.get("model", "unknown")), *values),
            )
            processed += 1
        offset = stream.tell()
        conn.execute("INSERT OR REPLACE INTO transcript_offsets VALUES (?,?,?,?,?)", (session_id, str(path), file_id, offset, int(skipping)))
    return {"status": "complete" if offset >= info.st_size and not skipping else "partial", "messages_seen": processed, "offset": offset}


def usage_summary(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT COUNT(DISTINCT session_id) AS sessions,COUNT(*) AS messages," +
                       ",".join(f"COALESCE(SUM({key}),0) AS {key}" for key in COUNTERS) + " FROM usage_messages").fetchone()
    return {**dict(row), "source": "provider usage in main-session transcripts", "billing": "not estimated"}


def record_run(conn: sqlite3.Connection, value: dict) -> dict:
    required = {"id", "task", "variant", "model", "quality", "elapsed_ms", *COUNTERS, "tool_calls", "failures"}
    if not isinstance(value, dict) or not required <= value.keys():
        raise ValueError(f"Task run requires {', '.join(sorted(required))}")
    if value["variant"] not in {"baseline", "memory"}:
        raise ValueError("variant must be baseline or memory")
    for key in ("id", "task", "model"):
        if not isinstance(value[key], str) or not 1 <= len(value[key]) <= 200:
            raise ValueError(f"Invalid {key}")
    for key in (*COUNTERS, "tool_calls", "failures"):
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
    for key in ("quality", "elapsed_ms", "cost_usd"):
        number = value.get(key)
        if key == "cost_usd" and number is None:
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
            raise ValueError(f"Invalid {key}")
    if value["quality"] > 1:
        raise ValueError("quality must be between 0 and 1")
    with conn:
        conn.execute("INSERT OR IGNORE INTO task_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     tuple(value[k] for k in ("id", "task", "variant", "model", "quality", "elapsed_ms", *COUNTERS, "tool_calls", "failures")) + (value.get("cost_usd"), time.time()))
    return {"recorded": value["id"], "comparisons": comparisons(conn)}


def comparisons(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT task,model,variant,COUNT(*) AS runs,AVG(quality) AS quality,AVG(elapsed_ms) AS elapsed_ms,"
        "AVG(input_tokens+output_tokens+cache_read_tokens+cache_creation_tokens) AS tokens,"
        "AVG(tool_calls) AS tool_calls,AVG(failures) AS failures,AVG(cost_usd) AS cost_usd "
        "FROM task_runs GROUP BY task,model,variant ORDER BY task,model",
    ).fetchall()
    groups: dict[tuple, dict] = {}
    for row in rows:
        groups.setdefault((row["task"], row["model"]), {})[row["variant"]] = dict(row)
    result = []
    for (task, model), variants in groups.items():
        baseline, memory = variants.get("baseline"), variants.get("memory")
        if not baseline or not memory:
            continue
        result.append({"task": task, "model": model, "baseline": baseline, "memory": memory,
                       "token_change_percent": round(100 * (memory["tokens"] / baseline["tokens"] - 1), 2) if baseline["tokens"] else None,
                       "quality_preserved": memory["quality"] >= baseline["quality"],
                       "note": "Observed task samples; not a guarantee of savings or subscription limits"})
    return result
