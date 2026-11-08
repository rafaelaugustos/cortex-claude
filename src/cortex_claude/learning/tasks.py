"""Compact, versioned work checkpoints in the one shared store."""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import TYPE_CHECKING

from cortex_claude.core.privacy import strip_private
from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.learning.extraction import terms, normalize
from cortex_claude.learning.policy import changed, snapshot

if TYPE_CHECKING:
    from cortex_claude.learning.store import LearningStore


def _clean(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("Task fields must be text")
    return " ".join(strip_private(text).split())


def save_task(store: LearningStore, cwd: str, sid: str | None, *, title: str,
              summary: str, next_step: str, decisions: list[str] | None = None,
              pending: list[str] | None = None, dependencies: list[str] | None = None,
              task_id: str | None = None, expected_revision: int | None = None) -> dict:
    from cortex_claude.learning.store import context_origin
    origin = context_origin(cwd)
    title, summary, next_step = _clean(title), _clean(summary), _clean(next_step)
    if not all((title, summary, next_step)) or len(title) > 120:
        raise ValueError("A title (up to 120 characters), summary and next_step are required")
    if any(not isinstance(items, list) or len(items) > 8 for items in (decisions or [], pending or [])):
        raise ValueError("At most 8 decisions and pending items")
    decisions = [item for value in decisions or [] if (item := _clean(value))]
    pending = [item for value in pending or [] if (item := _clean(value))]
    if count_tokens(json.dumps([title, summary, next_step, decisions, pending])) > 240:
        raise ValueError("Keep the complete checkpoint within 240 tokens")
    dependency_snapshot = snapshot(origin, dependencies or [])
    now = time.time()
    task_id = task_id or "task:" + uuid.uuid4().hex[:16]
    store.conn.execute("BEGIN IMMEDIATE")
    with store.conn:
        existing = store.conn.execute("SELECT * FROM work_items WHERE id=?", (task_id,)).fetchone()
        if existing and existing["origin"] != origin:
            raise ValueError("Update this task from its original repository")
        if not existing and expected_revision is not None:
            raise ValueError("Checkpoint no longer exists; save a new task instead")
        if existing and expected_revision != existing["revision"]:
            raise ValueError(f"Checkpoint changed; expected_revision must be {existing['revision']}")
        if existing and dependencies is None:
            dependency_snapshot = snapshot(origin, list(json.loads(existing["dependencies"])))
        revision = existing["revision"] + 1 if existing else 1
        store.conn.execute("INSERT OR REPLACE INTO work_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, origin, title, summary, json.dumps(decisions), json.dumps(pending), next_step,
             json.dumps(dependency_snapshot), revision, "open", sid or "manual", now, now + 14 * 86400))
    return {"id": task_id, "revision": revision, "state": "open"}


def task_detail(store: LearningStore, task_id: str, cwd: str | None = None) -> dict | None:
    from cortex_claude.learning.store import context_origin
    row = store.conn.execute("SELECT * FROM work_items WHERE id=?", (task_id,)).fetchone()
    if not row or (cwd is not None and row["origin"] != context_origin(cwd)):
        return None
    result = dict(row)
    for key in ("decisions", "pending", "dependencies"):
        result[key] = json.loads(result[key])
    result["needs_review"] = bool(row["expires_at"] < time.time() or changed(row["origin"], result["dependencies"]))
    automatic = store.conn.execute('SELECT client,files FROM automatic_checkpoints WHERE task_id=?', (task_id,)).fetchone()
    result['source'] = 'automatic' if automatic and row['session_id'].startswith('automatic:') else 'assistant'
    result['client'] = automatic['client'] if automatic else ''
    if automatic:
        from pathlib import Path
        result['needs_review'] = result['needs_review'] or any(not (Path(row['origin']) / name).is_file() for name in json.loads(automatic['files']))
    return result


def list_tasks(store: LearningStore, cwd: str | None = None) -> list[dict]:
    from cortex_claude.learning.store import context_origin
    rows = store.conn.execute("SELECT id FROM work_items " + ("WHERE origin=? " if cwd else "") + "ORDER BY updated_at DESC LIMIT 100", (context_origin(cwd),) if cwd else ()).fetchall()
    return [item for row in rows if (item := task_detail(store, row[0]))]


def update_state(store: LearningStore, task_id: str, state: str, expected_revision: int, cwd: str | None = None) -> dict:
    if state not in {"complete", "forget"}:
        raise ValueError("Use complete or forget")
    item = task_detail(store, task_id, cwd)
    if not item:
        raise ValueError("Task not found in this context")
    with store.conn:
        if state == "forget":
            cursor = store.conn.execute("DELETE FROM work_items WHERE id=? AND revision=?", (task_id, expected_revision))
        else:
            cursor = store.conn.execute("UPDATE work_items SET state='complete',revision=revision+1,updated_at=? WHERE id=? AND revision=?", (time.time(), task_id, expected_revision))
        if not cursor.rowcount:
            raise ValueError("Checkpoint changed; refresh before updating")
        if state == 'forget':
            store.conn.execute('DELETE FROM automatic_checkpoints WHERE task_id=?', (task_id,))
    return {"id": task_id, "state": state}


def resume_candidate(store: LearningStore, query: str, cwd: str, sid: str | None) -> dict | None:
    if not re.search(r"\b(?:retom\w*|continu\w*|resume|pick up|where we left|onde paramos)\b", normalize(query)):
        return None
    items = [item for item in list_tasks(store, cwd) if item["state"] == "open" and not item["needs_review"]]
    if not items:
        return None
    if len(items) > 1:
        scores = sorted(((len(terms(query) & terms(item["title"] + " " + item["summary"])), item) for item in items), key=lambda x: x[0], reverse=True)
        if scores[0][0] == 0 or scores[0][0] == scores[1][0]:
            return None
        item = scores[0][1]
    else:
        item = items[0]
    if sid and store.conn.execute("SELECT 1 FROM task_deliveries WHERE session_id=? AND task_id=? AND revision=?", (sid, item["id"], item["revision"])).fetchone():
        return None
    compact = {key: item[key] for key in ("title", "summary", "decisions", "pending", "next_step")}
    return {"id": item["id"], "revision": item["revision"], "line": f"- {item['id']} (work checkpoint; verify current files): " + json.dumps(compact, ensure_ascii=False)}


def handle_task(store: LearningStore, cwd: str, action: str, task_id: str | None = None,
                expected_revision: int | None = None, session_id: str | None = None, **fields) -> dict | list:
    if not store.config.enabled:
        return {"status": "disabled"}
    if action == "list":
        return list_tasks(store, cwd)
    if action == "save":
        return save_task(store, cwd, session_id, task_id=task_id, expected_revision=expected_revision, **fields)
    if action == "resume":
        item = task_detail(store, task_id or "", cwd)
        return item or {"status": "not-found"}
    if action in {"complete", "forget"}:
        return update_state(store, task_id or "", action, expected_revision or 0, cwd)
    raise ValueError("Unknown task action")
