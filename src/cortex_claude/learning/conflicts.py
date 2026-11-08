"""Keep ambiguous beliefs visible for review instead of silently choosing one."""
from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING

from cortex_claude.learning.extraction import Observation
from cortex_claude.learning.policy import clean_conditions

if TYPE_CHECKING:
    from cortex_claude.learning.store import LearningStore


def open_conflict(store: LearningStore, first: str, second: str, reason: str) -> str:
    left, right = sorted((first, second))
    cid = "conflict:" + hashlib.sha256(f"{left}:{right}".encode()).hexdigest()[:16]
    store.conn.execute("INSERT OR IGNORE INTO conflicts(id,left_id,right_id,reason,created_at) VALUES (?,?,?,?,?)", (cid, left, right, reason, time.time()))
    return cid


def detect(store: LearningStore, lesson_id: str) -> None:
    row = store.conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    if not row or row["kind"] != "preference":
        return
    others = store.conn.execute("SELECT id FROM lessons WHERE topic=? AND applicability=? AND origin=? AND conditions=? AND kind='preference' AND state IN ('active','candidate') AND id!=? AND signature!=?",
        (row["topic"], row["applicability"], row["origin"], row["conditions"], lesson_id, row["signature"])).fetchall()
    for other in others:
        open_conflict(store, lesson_id, other[0], "Different conclusions for the same topic and conditions")


def blocked_ids(store: LearningStore) -> set[str]:
    return {lid for row in store.conn.execute("SELECT left_id,right_id FROM conflicts WHERE state='open'") for lid in row}


def settle_replacement(store: LearningStore, lesson_id: str) -> None:
    store.conn.execute("UPDATE conflicts SET state='resolved',resolution='explicit-correction',resolved_at=? WHERE state='open' AND (left_id=? OR right_id=?)", (time.time(), lesson_id, lesson_id))


def list_conflicts(store: LearningStore, include_resolved: bool = False) -> list[dict]:
    rows = store.conn.execute("SELECT c.*,a.content AS left_content,a.conditions AS left_conditions,a.topic,b.content AS right_content,b.conditions AS right_conditions FROM conflicts c JOIN lessons a ON a.id=c.left_id JOIN lessons b ON b.id=c.right_id " + ("" if include_resolved else "WHERE c.state='open' ") + "ORDER BY c.created_at DESC LIMIT 100").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["left_evidence"] = (store.inspect(row["left_id"]) or {}).get("evidence", [])
        item["right_evidence"] = (store.inspect(row["right_id"]) or {}).get("evidence", [])
        result.append(item)
    return result


def resolve(store: LearningStore, conflict_id: str, choice: str,
            conditions: dict | None = None) -> dict:
    if choice not in {"keep_left", "keep_right", "condition_left", "condition_right"}:
        raise ValueError("Choose a conclusion or give one side a specific condition")
    cleaned = clean_conditions(conditions)
    if choice.startswith("condition") and not cleaned:
        raise ValueError("Provide conditions to separate the two rules")
    row = store.conn.execute("SELECT * FROM conflicts WHERE id=? AND state='open'", (conflict_id,)).fetchone()
    if not row:
        raise ValueError("This conflict is already resolved or no longer exists")
    chosen = row["left_id"] if choice.endswith("left") else row["right_id"]
    other = row["right_id"] if chosen == row["left_id"] else row["left_id"]
    if choice.startswith("condition"):
        lesson = store.conn.execute("SELECT * FROM lessons WHERE id=?", (chosen,)).fetchone()
        if json.dumps(cleaned, sort_keys=True) == store.conn.execute("SELECT conditions FROM lessons WHERE id=?", (other,)).fetchone()[0]:
            raise ValueError("Use a distinct condition for this rule")
        provenance = store.conn.execute("SELECT origin FROM evidence WHERE lesson_id=? ORDER BY observed_at DESC LIMIT 1", (chosen,)).fetchone()
        cwd = lesson["dependency_origin"] or (provenance[0] if provenance else lesson["origin"])
        # Reuse the normal correction pipeline to preserve scope, dependencies
        # and signatures rather than editing a unique identity in place.
        result = store.observe(Observation(lesson["content"], lesson["topic"], lesson["applicability"], lesson["triggers"], explicit=True, conditions=cleaned, dependencies=list(json.loads(lesson["dependencies"]))),
                               cwd, "human-resolution:" + conflict_id, source="human", replaces=chosen)
        chosen = result["id"]
    store.conn.execute("BEGIN IMMEDIATE")
    with store.conn:
        if choice.startswith("keep"):
            if not store.conn.execute("SELECT 1 FROM conflicts WHERE id=? AND state='open'", (conflict_id,)).fetchone():
                raise ValueError("This conflict changed; refresh before resolving")
            store.conn.execute("UPDATE lessons SET state='superseded',updated_at=? WHERE id=?", (time.time(), other))
            store.conn.execute("UPDATE lessons SET state=CASE WHEN applicability='context' THEN 'candidate' ELSE 'active' END,explicit=1,supersedes=?,updated_at=? WHERE id=?", (other, time.time(), chosen))
            settle_replacement(store, other)
        store.conn.execute("UPDATE conflicts SET state='resolved',resolution=?,resolved_at=? WHERE id=?", (choice, time.time(), conflict_id))
        store.conn.execute("DELETE FROM deliveries WHERE lesson_id IN (?,?)", (chosen, other))
    return {"id": conflict_id, "state": "resolved", "choice": choice, "kept": chosen}
