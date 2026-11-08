from __future__ import annotations

import json
from pathlib import Path

from cortex_claude.learning.extraction import Observation
from cortex_claude.learning.store import LearningStore
from cortex_claude.learning.config import LearningConfig
from cortex_claude.learning.semantic import SemanticClient
from cortex_claude.learning.experiences import read_details, recent_verifications, record_experience, record_outcome


def handle_learn(home: Path, cwd: str, action: str = "observe", content: str = "",
                 topic: str = "", applicability: str = "context", triggers: str = "",
                 explicit: bool = False, lesson_id: str | None = None, *,
                 conditions: dict[str, list[str]] | None = None, experience: dict[str, str] | None = None,
                 dependencies: list[str] | None = None, max_age_days: int | None = None,
                 verification_id: str | None = None, outcome: str = "passed",
                 session_id: str | None = None, max_tokens: int | None = None, query: str = "",
                 assessment: str = "") -> str:
    config = LearningConfig.load(home)
    with LearningStore(home, config, SemanticClient(home, config)) as store:
        sid = session_id or store.current_session(cwd)
        if action == "list":
            return json.dumps(store.list(limit=10), ensure_ascii=False)
        if action == "status":
            return json.dumps({**store.stats(), "verifications": recent_verifications(store, cwd, sid)})
        if action == "forget":
            if not lesson_id:
                return "lesson_id required"
            return json.dumps({"deleted": store.forget(lesson_id)})
        if action not in {"observe", "correct", "experience", "outcome", "read", "feedback"}:
            return "Unknown learning action"
        if not config.enabled:
            return json.dumps({"status": "disabled"})
        if action in {"observe", "experience"} and not topic.strip():
            return "A stable topic key is required (for example code.function-size)"
        if action == "correct" and not lesson_id:
            return "lesson_id required for a correction"
        try:
            if action == "feedback":
                from cortex_claude.learning.selection import feedback
                return json.dumps(feedback(store, lesson_id or "", cwd, session_id or store.delivery_session(cwd), assessment, query))
            if action == "read":
                return json.dumps(read_details(store, lesson_id or "", cwd, sid, query, max_tokens), ensure_ascii=False)
            if action == "outcome":
                return json.dumps(record_outcome(store, lesson_id or "", cwd, sid, outcome, verification_id))
            observation = Observation(content, topic or "correction", applicability, triggers, explicit,
                                      correction=action == "correct", conditions=conditions or {},
                                      dependencies=dependencies or [], max_age_days=max_age_days)
            if action == "experience":
                return json.dumps(record_experience(store, observation, experience or {}, cwd, sid, verification_id), ensure_ascii=False)
            result = store.observe(
                observation, cwd, sid, source="assistant",
                replaces=lesson_id if action == "correct" else None,
            )
        except ValueError as error:
            return str(error)
        return json.dumps(result, ensure_ascii=False)
