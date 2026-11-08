from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

from cortex_claude.core.privacy import strip_private
from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.learning.config import LearningConfig
from cortex_claude.learning.extraction import Observation, normalize, terms
from cortex_claude.learning.policy import applies, changed, clean_conditions, condition_key, describe_conditions, snapshot
from cortex_claude.learning.schema import upgrade
from cortex_claude.learning.semantic import SemanticClient, compatible, cosine
from cortex_claude.learning.selection import acknowledgement, already_supplied, usefulness, record_selection
from cortex_claude.learning.conflicts import blocked_ids, detect, open_conflict, settle_replacement

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learning_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO learning_meta VALUES ('schema_version', '1');
CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY, topic TEXT NOT NULL, signature TEXT NOT NULL,
    content TEXT NOT NULL, applicability TEXT NOT NULL, origin TEXT NOT NULL,
    triggers TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'candidate',
    explicit INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
    updated_at REAL NOT NULL, supersedes TEXT,
    UNIQUE(topic, signature, applicability, origin)
);
CREATE INDEX IF NOT EXISTS lessons_state ON lessons(state, applicability);
CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts USING fts5(lesson_id UNINDEXED, words);
CREATE TABLE IF NOT EXISTS evidence (
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL, origin TEXT NOT NULL, source TEXT NOT NULL,
    observed_at REAL NOT NULL, PRIMARY KEY(lesson_id, session_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, origin TEXT NOT NULL, last_seen REAL NOT NULL,
    injected_tokens INTEGER NOT NULL DEFAULT 0,
    avoided_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS deliveries (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    PRIMARY KEY(session_id, lesson_id)
);
"""


def context_origin(cwd: str) -> str:
    path = Path(cwd).expanduser().resolve()
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            return str(parent)
    return str(path)


def _signature(content: str) -> str:
    words = terms(content) - {"agora", "now", "actually", "verdade", "like"}
    if "dislike" in words:
        words.remove("dislike")
        words.add("not")
    # Keep negation: positive and negative preferences must never reinforce
    # each other, even when every other word is identical.
    signature = " ".join(sorted(words))
    if re.search(r"\b(?:over|instead of|rather than|em vez de|antes de|depois de)\b", normalize(content)):
        signature += ":order:" + hashlib.sha256(normalize(content).encode()).hexdigest()[:12]
    return signature


class LearningStore:
    """One shared database, with provenance rather than project databases.

    Reads and deliveries never create evidence. Each session can contribute
    at most one confirmation to a lesson, including retries and repeated tools.
    """

    def __init__(self, home: Path, config: LearningConfig | None = None, semantic: SemanticClient | None = None):
        self.home = home
        self.semantic = semantic
        self.config = config or LearningConfig.load(home)
        home.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(home / "learning.db", timeout=2)
        try:
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=FULL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            version = self.conn.execute("SELECT name FROM sqlite_master WHERE name='learning_meta'").fetchone()
            if version:
                row = self.conn.execute("SELECT value FROM learning_meta WHERE key='schema_version'").fetchone()
                if not row or row[0] not in {"1", "2", "3", "4", "5"}:
                    self.conn.close()
                    raise ValueError("Unsupported learning database version")
            self.conn.executescript(_SCHEMA)
            upgrade(self.conn)
        except Exception:
            self.conn.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.conn.close()

    def session(self, session_id: str | None, cwd: str, reset: bool = False) -> str:
        origin = context_origin(cwd)
        # Missing client identity must not manufacture a new confirmation on
        # every call. A manual client contributes at most once per day/context.
        sid = session_id or f"manual:{origin}:{time.strftime('%Y-%m-%d', time.gmtime())}"
        if len(sid) > 512:
            raise ValueError("session_id too long")
        with self.conn:
            self.conn.execute(
                "INSERT INTO sessions(id, origin, last_seen) VALUES (?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET origin=excluded.origin, last_seen=excluded.last_seen",
                (sid, origin, time.time()),
            )
            if reset:
                self.conn.execute("DELETE FROM deliveries WHERE session_id=?", (sid,))
                self.conn.execute("DELETE FROM detail_deliveries WHERE session_id=?", (sid,))
                self.conn.execute("DELETE FROM file_reads WHERE session_id=?", (sid,))
                self.conn.execute("DELETE FROM task_deliveries WHERE session_id=?", (sid,))
                self.conn.execute("DELETE FROM project_deliveries WHERE session_id=?", (sid,))
                self.conn.execute("UPDATE sessions SET injected_tokens=0, detail_tokens=0 WHERE id=?", (sid,))
            # Session receipts are ephemeral. Evidence remains durable.
            self.conn.execute("DELETE FROM sessions WHERE last_seen < ?", (time.time() - 30 * 86400,))
        return sid

    def current_session(self, cwd: str) -> str | None:
        rows = self.conn.execute(
            "SELECT id FROM sessions WHERE origin=? AND last_seen>? AND id NOT LIKE 'manual:%' ORDER BY last_seen ASC, id",
            (context_origin(cwd), time.time() - 1800),
        ).fetchall()
        # Concurrent sessions are ambiguous. Reuse an existing session instead
        # of inventing a third confirmation. This may under-count manual notes;
        # the prompt hook always has the authoritative session identity.
        return rows[0][0] if rows else None

    def delivery_session(self, cwd: str) -> str | None:
        rows = self.conn.execute("SELECT id FROM sessions WHERE origin=? AND last_seen>? AND id NOT LIKE 'manual:%'", (context_origin(cwd), time.time() - 1800)).fetchall()
        # Delta reads must never assume a concurrent client saw another
        # client's base. Ambiguous callers get a full response instead.
        return rows[0][0] if len(rows) == 1 else None

    def observe(self, observation: Observation, cwd: str, session_id: str | None = None,
                source: str = "user", replaces: str | None = None, *,
                kind: str = "preference", details: dict | None = None) -> dict:
        if not self.config.enabled:
            return {"status": "disabled"}
        content = " ".join(strip_private(observation.content).split())
        key = normalize(strip_private(observation.key))[:160]
        triggers = strip_private(observation.triggers)[:400]
        if not content:
            return {"status": "private-or-empty"}
        if count_tokens(content) > self.config.max_lesson_tokens:
            raise ValueError(f"Keep a lesson within {self.config.max_lesson_tokens} tokens; summarize without losing its conditions")
        if not key:
            raise ValueError("A stable topic key is required")
        if observation.applicability not in {"personal", "transferable", "context"}:
            raise ValueError("applicability must be personal, transferable or context")
        origin = context_origin(cwd)
        conditions = clean_conditions(observation.conditions)
        condition_json = json.dumps(conditions, sort_keys=True)
        dependencies = snapshot(origin, observation.dependencies)
        ttl = observation.max_age_days
        if ttl is not None and (type(ttl) is not int or not 1 <= ttl <= 3650):
            raise ValueError("max_age_days must be between 1 and 3650")
        expires = time.time() + ttl * 86400 if ttl else None
        if kind not in {"preference", "experience"}:
            raise ValueError("Unknown lesson kind")
        sid = self.session(session_id, cwd)
        signature = _signature(content)
        identity = condition_key(conditions)
        if kind == "experience":
            identity += json.dumps(details, sort_keys=True)
        if identity:
            signature += ":" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        vector = self.semantic.vectors([content]).get(content) if self.semantic else None
        applicability = observation.applicability
        boundary = origin if applicability == "context" else "*"
        explicit = observation.explicit if kind == "preference" else False
        now = time.time()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            old = None
            if replaces:
                old = self.conn.execute("SELECT * FROM lessons WHERE id=?", (replaces,)).fetchone()
                if not old:
                    raise ValueError("Lesson to correct does not exist")
                if old["kind"] != "preference":
                    raise ValueError("Record a revised experience and validate it instead of correcting it as a preference")
                key, applicability, boundary = old["topic"], old["applicability"], old["origin"]
                if not observation.conditions:
                    conditions = json.loads(old["conditions"])
                    condition_json = old["conditions"]
                    signature = _signature(content)
                    if conditions:
                        signature += ":" + hashlib.sha256(condition_key(conditions).encode()).hexdigest()[:16]
                if boundary != "*" and boundary != origin:
                    raise ValueError("Correct a contextual lesson from its original context")
                if old["dependencies"] != "{}" and not observation.dependencies:
                    if old["dependency_origin"] != origin:
                        raise ValueError("Correct a file-bound lesson from its original repository")
                    dependencies = snapshot(origin, list(json.loads(old["dependencies"])))
                if old["expires_at"] and observation.max_age_days is None:
                    expires = now + max(86400, old["expires_at"] - old["created_at"])
                explicit = explicit or old["state"] == "active"
            elif observation.correction:
                old = self.conn.execute(
                    "SELECT * FROM lessons WHERE topic=? AND applicability=? AND origin=? "
                    "AND conditions=? AND kind=? AND state IN ('active','candidate') ORDER BY updated_at DESC LIMIT 1",
                    (key, applicability, boundary, condition_json, kind),
                ).fetchone()
                explicit = explicit or bool(old and old["state"] == "active")

            row = self.conn.execute(
                "SELECT * FROM lessons WHERE topic=? AND signature=? AND applicability=? AND origin=?",
                (key, signature, applicability, boundary),
            ).fetchone()
            if not row and vector and kind == "preference" and not (observation.correction or replaces):
                row = self._equivalent(content, key, applicability, boundary, condition_json, vector)
                if row:
                    key, signature, content = row["topic"], row["signature"], row["content"]
            lesson_id = row["id"] if row else "learn:" + hashlib.sha256(
                json.dumps([key, signature, applicability, boundary], ensure_ascii=False).encode()
            ).hexdigest()[:16]
            if row and row["state"] == "stale" and not (observation.correction or replaces):
                self.conn.rollback()
                return {"id": lesson_id, "status": "stale", "reason": "Revalidation required"}
            if row and row["state"] == "superseded" and not (observation.correction or replaces or explicit):
                self.conn.rollback()
                return {"id": lesson_id, "status": "superseded", "reason": "An explicit correction is required to restore an old preference"}
            if old and old["id"] != lesson_id:
                self.conn.execute("UPDATE lessons SET state='superseded', updated_at=? WHERE id=?", (now, old["id"]))
                settle_replacement(self, old["id"])
            if not row:
                self.conn.execute(
                    "INSERT INTO lessons(id,topic,signature,content,applicability,origin,triggers,explicit,created_at,updated_at,supersedes) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (lesson_id, key, signature, content, applicability, boundary, triggers,
                     int(explicit), now, now, old["id"] if old and old["id"] != lesson_id else None),
                )
            else:
                if row["state"] in {"superseded", "stale"}:
                    self.conn.execute("DELETE FROM evidence WHERE lesson_id=?", (lesson_id,))
                    self.conn.execute("DELETE FROM deliveries WHERE lesson_id=?", (lesson_id,))
                    self.conn.execute("DELETE FROM detail_deliveries WHERE lesson_id=?", (lesson_id,))
                    self.conn.execute("UPDATE lessons SET dependencies=?,expires_at=?,stale_reason='' WHERE id=?",
                                      (json.dumps(dependencies), expires, lesson_id))
                self.conn.execute(
                    "UPDATE lessons SET explicit=MAX(explicit,?), updated_at=?, "
                    "state=CASE WHEN state IN ('superseded','stale') THEN 'candidate' ELSE state END WHERE id=?",
                    (int(explicit), now, lesson_id),
                )
            if not row:
                self.conn.execute(
                    "UPDATE lessons SET kind=?,conditions=?,details=?,dependencies=?,dependency_origin=?,expires_at=?,validation=? WHERE id=?",
                    (kind, condition_json, json.dumps(details or {}, ensure_ascii=False), json.dumps(dependencies),
                     origin, expires, "pending" if kind == "experience" else "not-required", lesson_id),
                )
            if kind == "preference":
                self.conn.execute("INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?)", (lesson_id, sid, origin, source, now))
            if vector and not row:
                self.conn.execute("INSERT OR REPLACE INTO lesson_vectors VALUES (?,?,?)",
                                  (lesson_id, self.config.semantic_model, json.dumps(vector)))
            counts = self.conn.execute(
                "SELECT COUNT(*) AS confirmations, COUNT(DISTINCT origin) AS contexts FROM evidence WHERE lesson_id=?",
                (lesson_id,),
            ).fetchone()
            permanent = self.conn.execute("SELECT explicit FROM lessons WHERE id=?", (lesson_id,)).fetchone()[0]
            enough = counts["confirmations"] >= self.config.confirmations
            diverse = applicability != "transferable" or counts["contexts"] >= self.config.min_contexts
            active = kind == "preference" and applicability != "context" and (permanent or (enough and diverse) or bool(row and row["state"] == "active"))
            if active:
                self.conn.execute("UPDATE lessons SET state='active' WHERE id=?", (lesson_id,))
                if explicit or observation.correction or replaces:
                    others = self.conn.execute("SELECT id FROM lessons WHERE topic=? AND applicability=? AND origin=? AND conditions=? AND kind='preference' AND id!=? AND state IN ('active','candidate')", (key, applicability, boundary, condition_json, lesson_id)).fetchall()
                    for other in others:
                        self.conn.execute("UPDATE lessons SET state='superseded',updated_at=? WHERE id=?", (now, other[0]))
                        settle_replacement(self, other[0])
            if not (explicit or observation.correction or replaces):
                detect(self, lesson_id)
            self.conn.execute("DELETE FROM lessons_fts WHERE lesson_id=?", (lesson_id,))
            self.conn.execute("INSERT INTO lessons_fts VALUES (?,?)", (lesson_id, " ".join(sorted(terms(content + " " + triggers + " " + key)))))
            self.conn.commit()
            final_state = self.conn.execute("SELECT state FROM lessons WHERE id=?", (lesson_id,)).fetchone()[0]
            return {"id": lesson_id, "status": final_state, **dict(counts),
                    "required": self.config.confirmations, "content": content}
        except Exception:
            self.conn.rollback()
            raise

    def _equivalent(self, content: str, key: str, applicability: str, boundary: str,
                    conditions: str, vector: list[float]):
        rows = self.conn.execute(
            "SELECT l.*,v.vector FROM lessons l JOIN lesson_vectors v ON v.lesson_id=l.id "
            "WHERE l.applicability=? AND l.origin=? AND l.conditions=? AND l.kind='preference' "
            "AND l.state IN ('active','candidate') AND v.model=? "
            "AND (l.topic=? OR (l.topic LIKE 'preference %' AND ? LIKE 'preference %'))",
            (applicability, boundary, conditions, self.config.semantic_model, key, key),
        ).fetchall()
        scored = sorted(((cosine(vector, json.loads(r["vector"])), r) for r in rows
                         if compatible(content, r["content"])), key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] < self.config.semantic_merge_threshold:
            return None
        # Ambiguous near-neighbours must not combine independent beliefs.
        if len(scored) > 1 and scored[0][0] - scored[1][0] < .03:
            return None
        return scored[0][1]

    def _fresh(self, row) -> bool:
        if row["state"] in {"superseded", "stale"}:
            return False
        reason = ""
        if row["expires_at"] and row["expires_at"] < time.time():
            reason = "validation expired"
        elif changed(row["dependency_origin"], json.loads(row["dependencies"])):
            reason = "dependency changed or unavailable"
        if reason:
            self.conn.execute("UPDATE lessons SET state='stale', stale_reason=? WHERE id=?", (reason, row["id"]))
            return False
        return True

    def _candidates(self, query: str, cwd: str, vector: list[float] | None = None) -> list[dict]:
        words = set(sorted(terms(strip_private(query)))[:48])
        origin = context_origin(cwd)
        # Apply origin and state gates before lexical OR semantic ranking.
        rows = self.conn.execute(
            "SELECT l.*,COUNT(e.lesson_id) AS confirmations,v.vector FROM lessons l "
            "LEFT JOIN evidence e ON e.lesson_id=l.id "
            "LEFT JOIN lesson_vectors v ON v.lesson_id=l.id AND v.model=? "
            "WHERE l.state IN ('active','candidate') AND (l.kind!='experience' OR l.validation='passed') "
            "AND (l.state='active' OR EXISTS (SELECT 1 FROM evidence x WHERE x.lesson_id=l.id AND x.origin=?)) "
            "AND (l.applicability!='context' OR l.origin=?) GROUP BY l.id",
            (self.config.semantic_model, origin, origin),
        ).fetchall()
        candidates = []
        for row in rows:
            conditions = json.loads(row["conditions"])
            if not applies(conditions, query):
                continue
            lexical = terms(row["content"] + " " + row["triggers"])
            overlap = len(words & lexical)
            semantic = cosine(vector, json.loads(row["vector"])) if vector and row["vector"] else 0
            if not overlap and row["triggers"] != "*" and not (conditions.get("all") or conditions.get("any")) and semantic < self.config.semantic_recall_threshold:
                continue
            if not self._fresh(row):
                continue
            score = overlap / max(len(lexical), 1) + min(row["confirmations"], 5) * .03
            score += max(0, semantic) * .4 + (.1 if row["state"] == "active" else 0)
            score += .4 if conditions else 0
            utility = usefulness(self, row["id"], query)
            candidates.append({**dict(row), "score": score * utility["factor"], "utility": utility, "conditions_data": conditions})
        # Specific rules override a generic preference only for matching tasks.
        conditional_topics = {r["topic"] for r in candidates if r["conditions_data"] and r["kind"] == "preference"}
        candidates = [r for r in candidates if r["conditions_data"] or r["topic"] not in conditional_topics or r["kind"] != "preference"]
        # Two equally specific rules that both apply need review. Generic
        # defaults were already removed above, so exceptions keep working.
        for i, first in enumerate(candidates):
            for second in candidates[i + 1:]:
                if first["kind"] == second["kind"] == "preference" and first["topic"] == second["topic"] and _signature(first["content"]) != _signature(second["content"]):
                    open_conflict(self, first["id"], second["id"], "Both rules apply to this task")
        return sorted(candidates, key=lambda r: (r["score"], r["updated_at"]), reverse=True)

    def context(self, query: str, cwd: str, session_id: str | None = None,
                max_tokens: int | None = None, delivered: bool = True,
                already_known: list[str] | None = None) -> dict:
        if not self.config.enabled or not strip_private(query).strip() or acknowledgement(query):
            return {"context": "", "tokens": 0, "ids": []}
        sid = self.session(session_id, cwd) if delivered else None
        limit = max(0, min(max_tokens if max_tokens is not None else self.config.max_context_tokens, 2000))
        vector = self.semantic.vectors([query]).get(query) if self.semantic else None
        prefix = "<cortex-memory>\nPrior observations; current instructions take precedence.\n"
        suffix = "\n</cortex-memory>"
        lines, selected, skipped = [], [], 0
        checkpoint = None
        project = None
        self.conn.execute("BEGIN IMMEDIATE")
        with self.conn:
            if sid:
                spent = self.conn.execute("SELECT injected_tokens+detail_tokens FROM sessions WHERE id=?", (sid,)).fetchone()[0]
                limit = min(limit, max(0, self.config.max_session_tokens - spent))
            for lid in already_known or []:
                if sid:
                    self.conn.execute("INSERT OR IGNORE INTO deliveries VALUES (?,?)", (sid, lid))
            candidates = self._candidates(query, cwd, vector)
            blocked = blocked_ids(self)
            from cortex_claude.learning.tasks import resume_candidate
            checkpoint = resume_candidate(self, query, cwd, sid)
            # Short or weakly matched tasks get a smaller automatic budget.
            # An explicit recall budget remains under the caller's control.
            if max_tokens is None and not checkpoint and (len(terms(query)) < 3 or (candidates and candidates[0]["score"] < .3)):
                limit = min(limit, 96)
            if checkpoint and count_tokens(prefix + checkpoint["line"] + suffix) <= limit:
                lines.append(checkpoint["line"])
            else:
                checkpoint = None
            for row in candidates:
                reason = ("conflict" if row["id"] in blocked else "already-in-prompt" if already_supplied(row["content"], query) else "low-usefulness" if row["utility"]["suppress"] else None)
                if reason:
                    record_selection(self, sid, row["id"], reason)
                    continue
                if sid and self.conn.execute("SELECT 1 FROM deliveries WHERE session_id=? AND lesson_id=?", (sid, row["id"])).fetchone():
                    skipped += count_tokens(row["content"])
                    continue
                label = "shared" if row["state"] == "active" else "this context"
                update = "; replaces previous preference" if row["supersedes"] else ""
                condition = describe_conditions(row["conditions_data"])
                qualifiers = f"; {condition}" if condition else ""
                if row["kind"] == "experience":
                    qualifiers += "; tested; details: cortex_learn action=read"
                line = f"- {row['id']} ({label}{update}{qualifiers}): {row['content']}"
                if count_tokens(prefix + "\n".join([*lines, line]) + suffix) > limit:
                    continue  # A long candidate must not hide a shorter one.
                lines.append(line)
                selected.append(row["id"])
                record_selection(self, sid, row["id"], "delivered")
                if len(selected) >= self.config.max_items:
                    break
            from cortex_claude.learning.projects import project_context
            project = project_context(self, query, cwd, sid)
            if project and count_tokens(prefix + "\n".join([*lines, project["line"]]) + suffix) <= limit:
                lines.append(project["line"])
            else:
                project = None
            context = prefix + "\n".join(lines) + suffix if lines else ""
            used = count_tokens(context)
            if sid:
                if project:
                    self.conn.execute("INSERT OR REPLACE INTO project_deliveries VALUES (?,?,?)", (sid, project["origin"], project["revision"]))
                if checkpoint:
                    self.conn.execute("INSERT OR REPLACE INTO task_deliveries VALUES (?,?,?)", (sid, checkpoint["id"], checkpoint["revision"]))
                self.conn.executemany("INSERT OR IGNORE INTO deliveries VALUES (?,?)", [(sid, lid) for lid in selected])
                self.conn.execute(
                    "UPDATE sessions SET injected_tokens=injected_tokens+?, avoided_tokens=avoided_tokens+? WHERE id=?",
                    (used, skipped, sid),
                )
        return {"context": context, "tokens": used, "ids": selected, "repeat_tokens_avoided": skipped,
                "task_id": checkpoint["id"] if checkpoint else None}

    def list(self, limit: int = 30) -> list[dict]:
        with self.conn:
            for row in self.conn.execute("SELECT * FROM lessons WHERE state IN ('active','candidate')").fetchall():
                self._fresh(row)
        blocked = blocked_ids(self)
        return [{**dict(row), "has_conflict": row["id"] in blocked,
                 "feedback": {r[0]: r[1] for r in self.conn.execute("SELECT assessment,COUNT(*) FROM feedback WHERE lesson_id=? GROUP BY assessment", (row["id"],))}} for row in self.conn.execute(
            "SELECT l.id,l.topic,l.content,l.state,l.applicability,l.origin,l.explicit,l.kind,l.conditions,l.validation,l.stale_reason,l.expires_at, "
            "COUNT(e.lesson_id) AS confirmations, COUNT(DISTINCT e.origin) AS contexts "
            "FROM lessons l LEFT JOIN evidence e ON e.lesson_id=l.id GROUP BY l.id "
            "ORDER BY l.updated_at DESC LIMIT ?", (max(1, min(limit, 100)),)
        )]

    def forget(self, lesson_id: str) -> bool:
        with self.conn:
            self.conn.execute("DELETE FROM lessons_fts WHERE lesson_id=?", (lesson_id,))
            return self.conn.execute("DELETE FROM lessons WHERE id=?", (lesson_id,)).rowcount > 0

    def inspect(self, lesson_id: str) -> dict | None:
        """Human inspection does not deliver context or reinforce a lesson."""
        row = self.conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        if not row:
            return None
        with self.conn:
            self._fresh(row)
        row = self.conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        result = dict(row)
        for field in ("conditions", "details", "dependencies"):
            result[field] = json.loads(result[field])
        result["evidence"] = [dict(r) for r in self.conn.execute(
            "SELECT origin,source,observed_at FROM evidence WHERE lesson_id=? ORDER BY observed_at DESC LIMIT 50", (lesson_id,))]
        result["outcomes"] = [dict(r) for r in self.conn.execute(
            "SELECT o.outcome,o.origin,o.observed_at,v.command FROM outcomes o LEFT JOIN verifications v ON v.id=o.verification_id WHERE o.lesson_id=? ORDER BY o.observed_at DESC LIMIT 50", (lesson_id,))]
        return result

    def stats(self) -> dict:
        from cortex_claude.learning.metrics import usage_summary, comparisons
        states = {r[0]: r[1] for r in self.conn.execute("SELECT state,COUNT(*) FROM lessons GROUP BY state")}
        totals = self.conn.execute("SELECT COALESCE(SUM(injected_tokens),0), COALESCE(SUM(avoided_tokens),0) FROM sessions").fetchone()
        semantic_status = "disabled" if not self.config.semantic_enabled else "unavailable"
        try:
            status = json.loads((self.home / "semantic-status.json").read_text())
            if self.config.semantic_enabled and status["model"] == self.config.semantic_model and time.time() - status["updated_at"] < 90:
                semantic_status = status["state"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return {"states": states, "confirmations_required": self.config.confirmations,
                "conflicts_open": self.conn.execute("SELECT COUNT(*) FROM conflicts WHERE state='open'").fetchone()[0],
                "selection": {r[0]: r[1] for r in self.conn.execute("SELECT reason,SUM(count) FROM selection_events GROUP BY reason")},
                "feedback": {r[0]: r[1] for r in self.conn.execute("SELECT assessment,COUNT(*) FROM feedback GROUP BY assessment")},
                "reads": dict(self.conn.execute("SELECT COALESCE(SUM(full_reads),0) AS full,COALESCE(SUM(delta_reads),0) AS delta,COALESCE(SUM(unchanged_reads),0) AS unchanged,COALESCE(SUM(emitted_tokens),0) AS emitted_tokens,COALESCE(SUM(avoided_tokens),0) AS avoided_tokens FROM read_metrics").fetchone()),
                "tasks_open": self.conn.execute("SELECT COUNT(*) FROM work_items WHERE state='open' AND expires_at>?", (time.time(),)).fetchone()[0],
                "injected_tokens": totals[0], "repeat_tokens_avoided": totals[1],
                "max_context_tokens": self.config.max_context_tokens,
                "max_session_tokens": self.config.max_session_tokens,
                "detail_tokens": self.conn.execute("SELECT COALESCE(SUM(detail_tokens),0) FROM sessions").fetchone()[0],
                "semantic_model": self.config.semantic_model,
                "semantic_status": semantic_status,
                "semantic_indexed": self.conn.execute("SELECT COUNT(*) FROM lesson_vectors WHERE model=?", (self.config.semantic_model,)).fetchone()[0],
                "usage": usage_summary(self.conn), "comparisons": comparisons(self.conn),
                "token_estimator": "cl100k_base; not provider billing"}
