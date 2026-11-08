import json
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

import pytest

from cortex_claude.hooks import process_event
from cortex_claude.learning.config import LearningConfig
from cortex_claude.learning.experiences import read_details, record_experience, record_outcome, record_verification
from cortex_claude.learning.extraction import Observation, extract_observations
from cortex_claude.learning.metrics import ingest_transcript, record_run, usage_summary
from cortex_claude.learning.semantic import compatible
from cortex_claude.learning.store import LearningStore, _SCHEMA
from cortex_claude.server.tools.learn import handle_learn


class Vectors:
    """Controlled similar embeddings to exercise independent semantic guards."""
    def vectors(self, texts):
        return {text: [1.0] + [0.0] * 383 for text in texts}


def note(text="Prefer concise responses", **kwargs):
    return Observation(text, "communication.detail", "personal", "*", **kwargs)


def receipt(store, cwd, sid, tool="test-1", passed=True):
    store.session(sid, str(cwd))
    return record_verification(store, {"cwd": str(cwd), "session_id": sid, "tool_name": "Bash",
        "tool_use_id": tool, "tool_input": {"command": "python -m pytest"},
        "tool_response": {"stdout": "3 passed" if passed else "1 failed", "exit_code": 0 if passed else 1}}, failed=not passed)


def episode(store, cwd, sid="first", verified=False, **kwargs):
    verification_id = receipt(store, cwd, sid) if verified else None
    return record_experience(store, Observation("Parse false environment flags explicitly", "env.flags", "transferable", "environment flags", **kwargs),
        {"situation": "String false enabled a feature", "cause": "bool of a nonempty string is true", "solution": "Normalize and compare with allowed true values"},
        str(cwd), sid, verification_id)


def test_v1_database_migrates_without_losing_evidence(tmp_path):
    conn = sqlite3.connect(tmp_path / "learning.db")
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO lessons VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("old", "test", "test", "Prefer tests", "personal", "*", "test", "active", 1, 1, 1, None))
    conn.execute("INSERT INTO evidence VALUES ('old','session','/old','user',1)")
    conn.commit()
    conn.close()
    for _ in range(2):
        with LearningStore(tmp_path) as store:
            assert store.list()[0]["confirmations"] == 1
            assert store.context("test", "/other", delivered=False)["ids"] == ["old"]
            assert store.conn.execute("SELECT value FROM learning_meta WHERE key='schema_version'").fetchone()[0] == "5"


def test_semantic_paraphrases_consolidate_without_counting_reads(tmp_path):
    with LearningStore(tmp_path, semantic=Vectors()) as store:
        first = store.observe(note("I prefer replies that get straight to the point"), "/a", "a")
        second = store.observe(note("I like succinct explanations"), "/a", "b")
        third = store.observe(note("Eu prefiro respostas sem enrolacao"), "/b", "c")
        # 'sem' is a negation guard, so a model alone may not prove equivalence.
        assert first["id"] == second["id"]
        assert third["id"] != first["id"]
        store.observe(note("I prefer direct answers"), "/b", "d")
        # Unproven equivalence now requires review instead of silently selecting a side.
        assert store.context("Any task", "/new", delivered=False)["ids"] == []
        from cortex_claude.learning.conflicts import list_conflicts, resolve
        conflict = list_conflicts(store)[0]
        resolve(store, conflict["id"], "keep_left" if conflict["left_id"] == first["id"] else "keep_right")
        assert store.context("Any task", "/new", delivered=False)["ids"] == [first["id"]]
        assert next(r for r in store.list() if r["id"] == first["id"])["confirmations"] == 3


def test_semantic_negation_conditions_and_technologies_do_not_merge(tmp_path):
    with LearningStore(tmp_path, semantic=Vectors()) as store:
        a = store.observe(note("I prefer small responses"), "/a", "one")
        b = store.observe(note("I dislike small responses"), "/a", "two")
        c = store.observe(note("I prefer large responses"), "/a", "three")
        d = store.observe(note("I prefer small responses", conditions={"all": ["architecture"]}), "/a", "four")
        assert len({a["id"], b["id"], c["id"], d["id"]}) == 4
    assert not compatible("Use pytest", "Use vitest")
    assert not compatible("Retry 3 times", "Retry 5 times")
    assert not compatible("Prefer Python over JavaScript", "Prefer JavaScript over Python")


def test_conditional_exception_overrides_default_only_when_applicable(tmp_path):
    with LearningStore(tmp_path) as store:
        default = store.observe(note(explicit=True), "/a", "one")
        exception = store.observe(note("Prefer detailed responses", explicit=True, conditions={"any": ["architecture", "debugging"], "none": ["email"]}), "/a", "two")
        assert store.context("Explain architecture", "/b", delivered=False)["ids"] == [exception["id"]]
        assert store.context("Write an email about architecture", "/b", delivered=False)["ids"] == [default["id"]]
        assert store.context("Write a poem", "/b", delivered=False)["ids"] == [default["id"]]
        assert all(row["state"] == "active" for row in store.list())


def test_automatic_conditional_preference_keeps_its_condition(tmp_path):
    observations = extract_observations("Sempre prefiro respostas detalhadas quando discutimos arquitetura")
    assert observations[0].conditions == {"all": ["architecture"]}
    with LearningStore(tmp_path) as store:
        store.observe(observations[0], "/a", "s")
        assert store.context("Explain the architecture", "/b", delivered=False)["ids"]
        assert not store.context("Write an email", "/b", delivered=False)["ids"]


def test_file_change_and_expiration_suspend_retrieval(tmp_path):
    source = tmp_path / "config.json"
    source.write_text('{"version":1}')
    with LearningStore(tmp_path / "data") as store:
        a = store.observe(Observation("Config uses version one", "config", "context", "config", dependencies=["config.json"]), str(tmp_path), "s")
        assert store.context("config", str(tmp_path), delivered=False)["ids"]
        source.write_text('{"version":2}')
        assert not store.context("config", str(tmp_path), delivered=False)["ids"]
        assert store.list()[0]["state"] == "stale"
        assert store.observe(Observation("Config uses version one", "config", "context", "config"), str(tmp_path), "later")["status"] == "stale"
        b = store.observe(note(explicit=True, max_age_days=1), str(tmp_path), "s")
        with store.conn:
            store.conn.execute("UPDATE lessons SET expires_at=0.1 WHERE id=?", (b["id"],))
        assert not store.context("responses", "/other", delivered=False)["ids"]
        assert a["id"] != b["id"]


def test_dependency_paths_cannot_escape_origin(tmp_path):
    (tmp_path / "repo").mkdir()
    (tmp_path / "outside").write_text("secret")
    with LearningStore(tmp_path / "data") as store:
        with pytest.raises(ValueError, match="inside"):
            store.observe(note(dependencies=["../outside"]), str(tmp_path / "repo"), "s")


def test_hypothesis_is_not_recalled_and_fake_verification_rejected(tmp_path):
    with LearningStore(tmp_path) as store:
        result = episode(store, "/a")
        assert result["validation"] == "pending"
        assert not store.context("environment flags", "/a", delivered=False)["ids"]
        with pytest.raises(ValueError, match="successful"):
            record_outcome(store, result["id"], "/a", "first", "passed", "invented")
        assert read_details(store, result["id"], "/a", "reader")["status"] == "needs-validation"


def test_validated_experience_transfers_only_after_independent_successes(tmp_path):
    with LearningStore(tmp_path) as store:
        result = episode(store, "/a", verified=True)
        assert result["validation"] == "passed" and result["confirmations"] == 1
        assert store.context("environment flags", "/a", delivered=False)["ids"] == [result["id"]]
        assert not store.context("environment flags", "/b", delivered=False)["ids"]
        for sid, cwd in [("second", "/a"), ("third", "/b")]:
            v = receipt(store, cwd, sid)
            result = record_outcome(store, result["id"], cwd, sid, "passed", v)
        assert result["status"] == "active" and result["confirmations"] == 3
        context = store.context("environment flags", "/c", "work")
        assert context["ids"] == [result["id"]]
        assert "bool of" not in context["context"]
        details = read_details(store, result["id"], "/c", "work")
        assert "bool of" in details["details"]["cause"]
        assert read_details(store, result["id"], "/c", "work")["status"] == "already-delivered"
        assert next(row for row in store.list() if row["id"] == result["id"])["confirmations"] == 3
        record_outcome(store, result["id"], "/c", "work", "failed")
        assert not store.context("environment flags", "/c", "work")["ids"]


def test_wrong_session_origin_or_failed_latest_check_cannot_validate(tmp_path):
    with LearningStore(tmp_path) as store:
        result = episode(store, "/a")
        good = receipt(store, "/a", "first", "good")
        receipt(store, "/a", "first", "bad", passed=False)
        for cwd, sid, verification in [("/b", "first", good), ("/a", "other", good), ("/a", "first", "latest")]:
            with pytest.raises(ValueError, match="successful"):
                record_outcome(store, result["id"], cwd, sid, "passed", verification)


def test_masked_commands_and_no_test_outputs_are_not_evidence(tmp_path):
    with LearningStore(tmp_path) as store:
        for command, output in [("echo pytest", "2 passed"), ("pytest || true", "2 passed"), ("pytest --help", "usage"), ("pytest", "1 passed, 2 failed")]:
            assert record_verification(store, {"session_id": "s", "tool_use_id": command, "tool_name": "Bash", "tool_input": {"command": command}, "tool_response": {"stdout": output}}) is None


def test_details_share_session_budget_and_repeated_outcome_does_not_reset_it(tmp_path):
    with LearningStore(tmp_path, LearningConfig(max_session_tokens=120)) as store:
        result = episode(store, "/a", verified=True)
        store.context("environment flags", "/a", "work")
        assert read_details(store, result["id"], "/a", "work")["status"] == "budget-exhausted"
        record_outcome(store, result["id"], "/a", "first", "passed", "latest")
        assert store.context("environment flags", "/a", "work")["tokens"] == 0


def test_real_hook_receipt_is_available_to_mcp_learning(tmp_path):
    process_event("SessionStart", {"session_id": "s", "cwd": "/a"}, tmp_path)
    process_event("PostToolUse", {"session_id": "s", "cwd": "/a", "tool_name": "Bash", "tool_use_id": "tool1", "tool_input": {"command": "python -m pytest"}, "tool_response": {"stdout": "2 passed", "exit_code": 0}}, tmp_path)
    result = json.loads(handle_learn(tmp_path, "/a", action="experience", content="Retry a serialization failure", topic="db.retry", applicability="transferable", triggers="database retry", experience={"situation": "Transaction conflict", "cause": "Concurrent write", "solution": "Retry transaction"}, verification_id="latest"))
    assert result["validation"] == "passed"


def test_stop_ingests_usage_without_repetition_or_private_text(tmp_path):
    transcript = tmp_path / "session.jsonl"
    def message(output):
        return {"type": "assistant", "sessionId": "s", "message": {"id": "msg1", "model": "model", "content": "PRIVATE_TEXT", "usage": {"input_tokens": 100, "output_tokens": output, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 50}}}
    transcript.write_text(json.dumps(message(2)) + "\n" + json.dumps(message(20)) + "\n")
    for _ in range(2):
        process_event("Stop", {"session_id": "s", "transcript_path": str(transcript)}, tmp_path / "data")
    with LearningStore(tmp_path / "data") as store:
        summary = usage_summary(store.conn)
        assert summary["messages"] == 1 and summary["output_tokens"] == 20
        assert summary["input_tokens"] == 100 and summary["cache_read_tokens"] == 200
        assert "PRIVATE_TEXT" not in "\n".join(store.conn.iterdump())
        with transcript.open("a") as stream:
            stream.write('{"type":')
        assert ingest_transcript(store.conn, "s", transcript)["status"] == "partial"
        assert usage_summary(store.conn)["messages"] == 1


def test_task_comparison_reports_quality_regression_and_deduplicates_runs(tmp_path):
    with LearningStore(tmp_path) as store:
        run = {"id": "one", "task": "flag-parser-v1", "model": "same-model", "variant": "baseline", "quality": 1., "elapsed_ms": 1000, "input_tokens": 100, "output_tokens": 100, "cache_read_tokens": 0, "cache_creation_tokens": 0, "tool_calls": 4, "failures": 1}
        assert record_run(store.conn, run)["comparisons"] == []
        record_run(store.conn, run)
        result = record_run(store.conn, {**run, "id": "two", "variant": "memory", "quality": 0., "input_tokens": 50})
        comparison = result["comparisons"][0]
        assert not comparison["quality_preserved"]
        assert comparison["baseline"]["runs"] == 1
        assert comparison["token_change_percent"] == -25


def test_explicit_revalidation_of_same_file_bound_fact(tmp_path):
    source = tmp_path / "settings.json"
    source.write_text('{"test":1}')
    with LearningStore(tmp_path / "data") as store:
        note = Observation("Settings contain a test key", "settings", "context", "settings", dependencies=["settings.json"], max_age_days=2)
        first = store.observe(note, str(tmp_path), "s")
        source.write_text('{"test":2}')
        assert not store.context("settings", str(tmp_path), delivered=False)["ids"]
        refreshed = store.observe(Observation(note.content, "settings"), str(tmp_path), "s2", replaces=first["id"])
        assert refreshed["status"] == "candidate"
        assert store.context("settings", str(tmp_path), delivered=False)["ids"]
        source.write_text('{"test":3}')
        assert not store.context("settings", str(tmp_path), delivered=False)["ids"]


def test_oversized_tool_record_does_not_hide_following_usage(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(json.dumps({"type": "user", "content": "x" * 8_500_000}) + "\n" + json.dumps({"type": "assistant", "message": {"id": "m", "usage": {"input_tokens": 7, "output_tokens": 3}}}) + "\n")
    with LearningStore(tmp_path / "data") as store:
        assert ingest_transcript(store.conn, "s", transcript)["status"] == "partial"
        assert ingest_transcript(store.conn, "s", transcript)["status"] == "complete"
        assert usage_summary(store.conn)["input_tokens"] == 7


def test_complex_conditional_preferences_require_interpretation():
    assert extract_observations("I prefer long answers only if the problem is complex") == []
    assert extract_observations("Prefiro respostas curtas exceto quando discutimos arquitetura") == []


def test_parallel_hooks_cannot_overspend_the_session_budget(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(3)
    class ReadyTogether:
        def vectors(self, texts):
            barrier.wait(timeout=5)
            return {}
    config = LearningConfig(max_context_tokens=70, max_session_tokens=100)
    with LearningStore(tmp_path, config) as store:
        for language in ['python', 'rust', 'go']:
            store.observe(Observation(f'Prefer clear {language}', language, 'personal', language, True), '/a', 'seed')
    def read(language):
        with LearningStore(tmp_path, config, ReadyTogether()) as store:
            return store.context(language, '/b', 'parallel')['tokens']
    with ThreadPoolExecutor(max_workers=3) as workers:
        tokens = list(workers.map(read, ['python', 'rust', 'go']))
    assert 0 < sum(tokens) <= 100
