"""Decide whether a lesson adds information and learn from explicit feedback."""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import TYPE_CHECKING

from cortex_claude.core.privacy import strip_private
from cortex_claude.learning.extraction import normalize, terms
from cortex_claude.learning.semantic import compatible

if TYPE_CHECKING:
    from cortex_claude.learning.store import LearningStore


def task_keys(query: str) -> set[str]:
    # Retain matching cues without storing another copy of a private prompt.
    return {hashlib.sha256(word.encode()).hexdigest()[:16] for word in sorted(terms(strip_private(query)))[:48]}


def acknowledgement(query: str) -> bool:
    return normalize(query) in {"ok", "okay", "sim", "yes", "nao", "no", "obrigado", "obrigada", "valeu", "thanks", "thank you", "pronto", "entendi", "beleza", "bom dia", "oi", "ola", "hi", "hello"}


def already_supplied(content: str, query: str) -> bool:
    clean = strip_private(query)
    # A question mentioning the same terms is not the answer to itself.
    if "?" in clean or re.search(r"\b(?:como|qual|quais|why|how|what|whether|sera)\b", normalize(clean)):
        return False
    if not compatible(content, clean):
        return False
    wanted = terms(content)
    supplied = terms(clean)
    # Exact normalized statements or complete conceptual coverage are safe
    # abstentions; partial overlap still retrieves the missing information.
    return len(wanted) >= 3 and wanted <= supplied


def feedback(store: LearningStore, lesson_id: str, cwd: str, sid: str | None,
             assessment: str, query: str = "", source: str = "assistant") -> dict:
    from cortex_claude.learning.store import context_origin
    if assessment not in {"useful", "irrelevant", "corrected"}:
        raise ValueError("assessment must be useful, irrelevant or corrected")
    lesson = store.conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    if not lesson:
        raise ValueError("Lesson not found")
    if not sid:
        raise ValueError("A session_id is required for feedback")
    origin = context_origin(cwd)
    if source != "human":
        session = store.conn.execute("SELECT origin FROM sessions WHERE id=?", (sid,)).fetchone()
        delivered = store.conn.execute("SELECT 1 FROM deliveries WHERE lesson_id=? AND session_id=? UNION SELECT 1 FROM detail_deliveries WHERE lesson_id=? AND session_id=?", (lesson_id, sid, lesson_id, sid)).fetchone()
        if not session or session[0] != origin or not delivered:
            raise ValueError("Only give feedback on a lesson delivered in this session/context")
    with store.conn:
        store.conn.execute("INSERT INTO feedback VALUES (?,?,?,?,?,?,?) ON CONFLICT(lesson_id,session_id) DO UPDATE SET assessment=excluded.assessment,task_terms=excluded.task_terms,source=excluded.source,updated_at=excluded.updated_at",
            (lesson_id, sid, origin, assessment, json.dumps(sorted(task_keys(query))), source, time.time()))
    return {"id": lesson_id, "assessment": assessment, "evidence_unchanged": True}


def usefulness(store: LearningStore, lesson_id: str, query: str) -> dict:
    keys = task_keys(query)
    positive = negative = 0
    for row in store.conn.execute("SELECT assessment,task_terms FROM feedback WHERE lesson_id=? AND updated_at>?", (lesson_id, time.time() - 90 * 86400)):
        cues = set(json.loads(row["task_terms"]))
        if cues and len(cues & keys) / max(1, len(cues | keys)) < .5:
            continue
        if row["assessment"] == "useful":
            positive += 1
        else:
            negative += 1
    probability = (positive + 1) / (positive + negative + 2)
    return {"positive": positive, "negative": negative, "factor": .5 + probability,
            "suppress": negative >= 3 and probability < .3}


def record_selection(store: LearningStore, sid: str | None, lesson_id: str, reason: str) -> None:
    if sid:
        store.conn.execute("INSERT INTO selection_events(session_id,lesson_id,reason) VALUES (?,?,?) ON CONFLICT(session_id,lesson_id,reason) DO UPDATE SET count=count+1", (sid, lesson_id, reason))
