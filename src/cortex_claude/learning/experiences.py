"""Reusable episodes backed by actual test receipts, with progressive reading."""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import TYPE_CHECKING

from cortex_claude.core.privacy import strip_private
from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.learning.extraction import Observation
from cortex_claude.learning.policy import snapshot

if TYPE_CHECKING:
    from cortex_claude.learning.store import LearningStore


def record_verification(store: LearningStore, payload: dict, failed: bool = False) -> str | None:
    from cortex_claude.learning.store import context_origin
    command = (payload.get("tool_input") or {}).get("command", "")
    tool_id, sid = payload.get("tool_use_id"), payload.get("session_id")
    if payload.get("tool_name") != "Bash" or not isinstance(command, str) or not tool_id or not sid:
        return None
    # Never mistake echo/grep, suppressed failures or a background process for
    # a completed verification. Unsupported runners remain unverified.
    if re.search(r"\|\||(?<!\|)\|(?!\|)|;|(?<!&)&(?!&)|`|\$\(", command):
        return None
    runner = r"(?:^|&&)\s*(?:(?:\S*/)?(?:python[\d.]*\s+-m\s+)?pytest\b|(?:npm|pnpm|yarn)\s+(?:run\s+)?test\b|(?:npx\s+)?(?:vitest|jest)\b|cargo\s+test\b|go\s+test\b|(?:\S*/)?python[\d.]*\s+-m\s+unittest\b)"
    if not re.search(runner, command):
        return None
    response = payload.get("tool_response") or {}
    if isinstance(response, dict):
        passed = not failed and response.get("exit_code", response.get("exitCode", 0)) == 0 and not response.get("interrupted")
        output = str(response.get("stdout", "")) + "\n" + str(response.get("stderr", ""))
    else:
        passed, output = not failed, str(response)
    # Exit zero alone is insufficient (help, no tests, or a wrapper command).
    summary = re.search(r"\b[1-9]\d* passed\b|\bPASS\b|\bOK\b|test result: ok|(?m:^ok\s+\S+)", output)
    if passed and (not summary or re.search(r"\b[1-9]\d* (?:failed|errors?)\b|\bFAIL(?:ED)?\b", output)):
        return None
    origin = context_origin(payload.get("cwd", "."))
    receipt = "verify:" + hashlib.sha256(f"{sid}:{tool_id}".encode()).hexdigest()[:16]
    with store.conn:
        store.conn.execute("INSERT OR IGNORE INTO verifications VALUES (?,?,?,?,?,?)",
                           (receipt, sid, origin, strip_private(command)[:500], int(passed), time.time()))
    return receipt


def recent_verifications(store: LearningStore, cwd: str, sid: str | None) -> list[dict]:
    from cortex_claude.learning.store import context_origin
    return [dict(r) for r in store.conn.execute(
        "SELECT id,command,passed FROM verifications WHERE session_id=? AND origin=? AND observed_at>? ORDER BY observed_at DESC LIMIT 5",
        (sid, context_origin(cwd), time.time() - 3600),
    )]


def record_experience(store: LearningStore, observation: Observation, details: dict,
                      cwd: str, sid: str | None, verification_id: str | None = None) -> dict:
    if observation.applicability == "personal":
        raise ValueError("Experiences use context or transferable applicability")
    if not isinstance(details, dict) or set(details) != {"situation", "cause", "solution"}:
        raise ValueError("experience requires situation, cause and solution")
    if any(not isinstance(v, str) for v in details.values()):
        raise ValueError("Experience fields must be strings")
    clean = {k: strip_private(v).strip() for k, v in details.items()}
    if any(not v for v in clean.values()) or count_tokens(json.dumps(clean)) > store.config.max_detail_tokens:
        raise ValueError(f"Provide non-private experience details within {store.config.max_detail_tokens} tokens")
    if observation.max_age_days is None:
        observation.max_age_days = store.config.experience_ttl_days
    # Reject bad verification before mutating the episode.
    if verification_id:
        _verification(store, cwd, sid, verification_id)
    result = store.observe(observation, cwd, sid, source="episode", kind="experience", details=clean)
    if verification_id and result.get("id"):
        return record_outcome(store, result["id"], cwd, sid, "passed", verification_id)
    return {**result, "validation": "pending", "verifications": recent_verifications(store, cwd, sid)}


def _verification(store: LearningStore, cwd: str, sid: str | None, receipt: str):
    from cortex_claude.learning.store import context_origin
    if not sid:
        raise ValueError("A known session is required to link a verification")
    row = store.conn.execute(
        "SELECT * FROM verifications WHERE session_id=? AND origin=? AND observed_at>? "
        + ("" if receipt == "latest" else "AND id=? ") + "ORDER BY observed_at DESC LIMIT 1",
        (sid, context_origin(cwd), time.time() - 3600, *(() if receipt == "latest" else (receipt,))),
    ).fetchone()
    if not row or not row["passed"]:
        raise ValueError("A successful test receipt from this session/context within the last hour is required")
    return row


def record_outcome(store: LearningStore, lesson_id: str, cwd: str, sid: str | None,
                   outcome: str, verification_id: str | None = None) -> dict:
    from cortex_claude.learning.store import context_origin
    if outcome not in {"passed", "failed"}:
        raise ValueError("outcome must be passed or failed")
    row = store.conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    if not row or row["kind"] != "experience" or row["state"] == "superseded":
        raise ValueError("An existing experience is required")
    origin = context_origin(cwd)
    if row["applicability"] == "context" and row["origin"] != origin:
        raise ValueError("Validate a contextual experience in its original repository")
    receipt = _verification(store, cwd, sid, verification_id or "") if outcome == "passed" else None
    sid = store.session(sid, cwd)
    deps = json.loads(row["dependencies"])
    if deps and row["dependency_origin"] != origin:
        if not store._fresh(row):
            store.conn.commit()
            raise ValueError("Revalidate changed dependencies in their original repository")
    elif deps and outcome == "passed":
        assert receipt is not None
        deps = snapshot(origin, list(deps))
        # A successful check predating the last file edit cannot revalidate it.
        from pathlib import Path
        if any((Path(origin) / path).stat().st_mtime > receipt["observed_at"] for path in deps):
            raise ValueError("Run verification after the dependency changes")
    now = time.time()
    store.conn.execute("BEGIN IMMEDIATE")
    with store.conn:
        previous = store.conn.execute("SELECT verification_id,outcome FROM outcomes WHERE lesson_id=? AND session_id=?", (lesson_id, sid)).fetchone()
        if previous and previous["outcome"] == outcome and previous["verification_id"] == (receipt["id"] if receipt else None):
            return {"id": lesson_id, "status": row["state"], "validation": row["validation"], "duplicate": True}
        store.conn.execute("INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?,?,?)",
                           (lesson_id, sid, origin, outcome, receipt["id"] if receipt else None, now))
        if outcome == "passed":
            store.conn.execute("INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?)", (lesson_id, sid, origin, "verified-outcome", now))
        else:
            store.conn.execute("DELETE FROM evidence WHERE lesson_id=? AND session_id=?", (lesson_id, sid))
        counts = store.conn.execute("SELECT COUNT(*) AS confirmations,COUNT(DISTINCT origin) AS contexts FROM evidence WHERE lesson_id=?", (lesson_id,)).fetchone()
        active = (outcome == "passed" and row["applicability"] == "transferable"
                  and counts["confirmations"] >= store.config.confirmations and counts["contexts"] >= store.config.min_contexts)
        state = ("active" if active else "candidate") if outcome == "passed" else "stale"
        store.conn.execute("UPDATE lessons SET validation=?,state=?,stale_reason=?,updated_at=?,dependencies=?,expires_at=? WHERE id=?",
                           (outcome, state, "failed verification" if outcome == "failed" else "", now,
                            json.dumps(deps), now + store.config.experience_ttl_days * 86400, lesson_id))
        # A changed validation state must be visible even in an ongoing session.
        store.conn.execute("DELETE FROM deliveries WHERE lesson_id=?", (lesson_id,))
        store.conn.execute("DELETE FROM detail_deliveries WHERE lesson_id=?", (lesson_id,))
    return {"id": lesson_id, "status": state, "validation": outcome, **dict(counts)}


def read_details(store: LearningStore, lesson_id: str, cwd: str, sid: str | None,
                 query: str = "", max_tokens: int | None = None) -> dict:
    from cortex_claude.learning.policy import applies
    from cortex_claude.learning.store import context_origin
    row = store.conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    origin = context_origin(cwd)
    if not row:
        return {"status": "not-found"}
    from cortex_claude.learning.conflicts import blocked_ids
    if lesson_id in blocked_ids(store):
        return {"status": "needs-review", "reason": "Resolve the conflicting conclusions first"}
    local = store.conn.execute("SELECT 1 FROM evidence WHERE lesson_id=? AND origin=?", (lesson_id, origin)).fetchone()
    with store.conn:
        fresh = store._fresh(row)
    if not fresh or row["validation"] == "pending":
        return {"status": "needs-validation", "reason": row["stale_reason"] or "Expired, changed or unverified"}
    if (row["applicability"] == "context" and row["origin"] != origin) or (row["state"] != "active" and not local):
        return {"status": "unavailable-in-this-context"}
    if not applies(json.loads(row["conditions"]), query):
        return {"status": "conditions-not-met"}
    sid = store.session(sid, cwd)
    limit = max(0, min(max_tokens if max_tokens is not None else store.config.max_detail_tokens, store.config.max_detail_tokens))
    store.conn.execute("BEGIN IMMEDIATE")
    with store.conn:
        if store.conn.execute("SELECT 1 FROM detail_deliveries WHERE session_id=? AND lesson_id=?", (sid, lesson_id)).fetchone():
            return {"status": "already-delivered", "id": lesson_id}
        spent = store.conn.execute("SELECT injected_tokens+detail_tokens FROM sessions WHERE id=?", (sid,)).fetchone()[0]
        limit = min(limit, max(0, store.config.max_session_tokens - spent))
        evidence = store.conn.execute("SELECT origin,source FROM evidence WHERE lesson_id=? ORDER BY observed_at DESC LIMIT 3", (lesson_id,)).fetchall()
        result = {"id": lesson_id, "content": row["content"], "conditions": json.loads(row["conditions"]),
                  "validation": row["validation"], "details": json.loads(row["details"]),
                  "evidence": [dict(e) for e in evidence]}
        used = count_tokens(json.dumps(result, ensure_ascii=False))
        if used > limit:
            return {"status": "budget-exhausted", "required_tokens": used, "available_tokens": limit}
        store.conn.execute("INSERT INTO detail_deliveries VALUES (?,?,?)", (sid, lesson_id, used))
        store.conn.execute("UPDATE sessions SET detail_tokens=detail_tokens+? WHERE id=?", (used, sid))
        return result
