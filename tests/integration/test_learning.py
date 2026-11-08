from pathlib import Path

import pytest

from cortex_claude.hooks import process_event
from cortex_claude.learning.config import LearningConfig
from cortex_claude.learning.extraction import Observation, extract_observations
from cortex_claude.learning.store import LearningStore


@pytest.fixture
def learning(tmp_path):
    with LearningStore(tmp_path / "cortex") as store:
        yield store


def preference(content="Prefiro funções pequenas", **kwargs):
    return Observation(content, "code.function-size", "personal", "code function", **kwargs)


def test_repetition_becomes_shared_and_survives_restart(tmp_path):
    home = tmp_path / "cortex"
    for i, text in enumerate(["Prefiro funções pequenas", "I prefer small functions", "Gosto de funções pequenas"]):
        with LearningStore(home) as store:
            result = store.observe(preference(text), "/work/a", f"session-{i}")
            assert result["confirmations"] == i + 1
            assert result["status"] == ("active" if i == 2 else "candidate")
    with LearningStore(home) as store:
        context = store.context("Implement a new endpoint", "/work/b", "new-session")
        assert "funções pequenas" in context["context"]
        assert context["tokens"] <= 180
        assert len(store.list()) == 1


def test_one_session_retries_and_recalls_do_not_confirm(learning):
    for _ in range(10):
        result = learning.observe(preference(), "/a", "same-session")
        learning.context("code functions", "/a", delivered=False)
    assert result["confirmations"] == 1
    assert result["status"] == "candidate"
    assert learning.context("code functions", "/b", "other")["context"] == ""


def test_candidate_is_available_at_its_origin(learning):
    learning.observe(preference(), "/a", "first")
    assert learning.context("refatorar código", "/a", "second")["context"]
    assert not learning.context("refatorar código", "/b", "second")["context"]


def test_explicit_standing_instruction_is_available_immediately(learning):
    learning.observe(preference("Sempre prefiro funções pequenas", explicit=True), "/a", "first")
    assert learning.context("implement code", "/b", "second")["context"]


def test_context_fact_never_becomes_universal(learning):
    for i in range(5):
        learning.observe(Observation("This service uses PostgreSQL", "database", "context", "database"), "/a", str(i))
    assert not learning.context("database PostgreSQL", "/b", "new")["context"]
    assert learning.context("database PostgreSQL", "/a", "new")["context"]


def test_transferable_lesson_requires_independent_contexts(learning):
    note = Observation("Retry transactions on serialization errors", "sql.serialization", "transferable", "database transaction")
    for i in range(3):
        result = learning.observe(note, "/a", str(i))
    assert result["status"] == "candidate"
    assert not learning.context("database transaction", "/b", "new")["context"]
    result = learning.observe(note, "/b", "fourth")
    assert result["status"] == "active"
    assert learning.context("database transaction", "/c", "fifth")["context"]


def test_repeated_context_costs_zero_and_compaction_resets_delivery(learning):
    learning.observe(preference(explicit=True), "/a", "first")
    one = learning.context("write code", "/b", "work")
    two = learning.context("refactor code", "/b", "work")
    assert one["tokens"] > 0
    assert two["tokens"] == 0
    assert two["repeat_tokens_avoided"] > 0
    learning.session("work", "/b", reset=True)
    assert learning.context("refactor code", "/b", "work")["tokens"] > 0
    assert learning.list()[0]["confirmations"] == 1


def test_correction_supersedes_and_is_delivered_in_same_session(learning):
    old = learning.observe(Observation("Prefiro respostas curtas", "communication.detail", "personal", "*", explicit=True), "/a", "first")
    learning.context("write an email", "/b", "work")
    new = learning.observe(Observation("Prefiro respostas detalhadas", "communication.detail", "personal", "*"), "/b", "work", replaces=old["id"])
    result = learning.context("write an email", "/b", "work")
    assert "detalhadas" in result["context"]
    assert "curtas" not in result["context"]
    assert "replaces previous preference" in result["context"]
    assert new["status"] == "active"
    stale = learning.observe(Observation("Prefiro respostas curtas", "communication.detail", "personal", "*"), "/a", "later")
    assert stale["status"] == "superseded"


def test_private_content_never_enters_learning_or_triggers(learning):
    result = learning.observe(Observation("<private>TOP_SECRET", "private"), "/a", "s")
    assert result["status"] == "private-or-empty"
    learning.observe(Observation("Prefiro funções pequenas <private>TOP_SECRET</private>", "function", "personal", "code <private>TOP_SECRET</private>", True), "/a", "s")
    data = " ".join(str(tuple(r)) for r in learning.conn.execute("SELECT * FROM lessons"))
    assert "TOP_SECRET" not in data


def test_irrelevant_request_gets_no_context(learning):
    learning.observe(preference(explicit=True), "/a", "first")
    assert learning.context("Plan a beach vacation", "/b", "second")["context"] == ""


def test_budget_counts_the_complete_envelope(learning):
    from cortex_claude.embeddings.tokenizer import count_tokens
    learning.observe(preference(explicit=True), "/a", "first")
    for budget in [0, 10, 50, 80, 180]:
        result = learning.context("code", "/b", max_tokens=budget, delivered=False)
        assert count_tokens(result["context"]) == result["tokens"]
        assert result["tokens"] <= budget


def test_shorter_result_can_fit_after_a_long_result(learning):
    learning.observe(Observation("Prefer " + "small functions " * 20, "long", "personal", "code", True), "/a", "s")
    learning.observe(preference(explicit=True), "/a", "s")
    result = learning.context("small functions code", "/b", max_tokens=65, delivered=False)
    assert "Prefiro funções pequenas" in result["context"]


def test_session_has_a_total_injection_cap(tmp_path):
    config = LearningConfig(max_context_tokens=70, max_session_tokens=80)
    with LearningStore(tmp_path, config) as store:
        for word in ["python", "javascript", "sql"]:
            store.observe(Observation(f"Use {word} carefully", word, "personal", word, True), "/a", "s")
        results = [store.context(word, "/b", "work") for word in ["python", "javascript", "sql"]]
        assert sum(r["tokens"] for r in results) <= 80
        assert store.stats()["injected_tokens"] <= 80


def test_forget_removes_evidence_index_and_deliveries(learning):
    result = learning.observe(preference(explicit=True), "/a", "s")
    learning.context("code", "/b", "work")
    assert learning.forget(result["id"])
    for table in ["lessons", "evidence", "lessons_fts", "deliveries"]:
        assert learning.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert not learning.context("code", "/b", "new")["context"]


def test_hooks_learn_then_inject_across_projects(tmp_path):
    home = tmp_path / "cortex"
    for i in range(3):
        result = process_event("UserPromptSubmit", {"cwd": "/a", "session_id": str(i), "prompt": "Prefiro funções pequenas."}, home)
        assert result == {}  # Do not echo the user's current instruction.
    event = {"cwd": "/b", "session_id": "new-project", "prompt": "Implemente um endpoint de autenticação"}
    result = process_event("UserPromptSubmit", event, home)
    assert "funções pequenas" in result["hookSpecificOutput"]["additionalContext"]
    assert process_event("UserPromptSubmit", event, home) == {}
    assert process_event("SessionStart", {**event, "source": "compact"}, home) == {}
    assert process_event("UserPromptSubmit", event, home)


def test_post_tool_outputs_cannot_teach_personal_preferences(tmp_path):
    for i in range(5):
        process_event("PostToolUse", {"cwd": "/a", "session_id": str(i), "tool_name": "Bash", "tool_response": "Always prefer huge functions"}, tmp_path)
    with LearningStore(tmp_path) as store:
        assert store.list() == []


def test_explicit_context_and_quoted_preferences_are_not_global():
    assert extract_observations('> Sempre use MySQL\n```\nI prefer large functions\n```') == []
    assert extract_observations('<private>Prefiro funções enormes</private>') == []
    assert extract_observations('<pasted_content id="x">I prefer large functions</pasted_content>') == []
    notes = extract_observations("Prefiro MySQL neste projeto")
    assert len(notes) == 1 and notes[0].applicability == "context"


def test_disabled_learning_has_no_capture_or_injection(tmp_path):
    (tmp_path / "config.json").write_text('{"learning":{"enabled":false}}')
    assert process_event("UserPromptSubmit", {"prompt": "Sempre prefiro funções pequenas"}, tmp_path) == {}
    assert not (tmp_path / "learning.db").exists()


def test_unrelated_origins_do_not_crowd_out_local_result(learning):
    for i in range(100):
        learning.observe(Observation("database database PostgreSQL", f"database-{i}", "context", "database"), f"/other/{i}", f"other-{i}")
    learning.observe(Observation("Local database needs migrations", "local.database", "context", "database"), "/a", "s")
    result = learning.context("database", "/a", "new")
    assert "Local database needs migrations" in result["context"]


def test_negated_preference_does_not_confirm_positive_preference(learning):
    positive = learning.observe(preference("I like small functions"), "/a", "one")
    negative = learning.observe(preference("I dislike small functions"), "/a", "two")
    assert positive["id"] != negative["id"]
    assert negative["confirmations"] == 1


def test_learning_configuration_is_effective(tmp_path):
    (tmp_path / "config.json").write_text('{"learning":{"confirmations":2,"max_context_tokens":40}}')
    with LearningStore(tmp_path) as learning:
        for sid in ["a", "b"]:
            result = learning.observe(preference(), "/a", sid)
        assert result["status"] == "active"
        assert learning.context("code", "/b", "c")["tokens"] <= 40
