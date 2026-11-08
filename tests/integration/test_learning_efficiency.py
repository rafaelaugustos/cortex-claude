import json

import pytest

from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.learning.conflicts import list_conflicts, resolve
from cortex_claude.learning.experiences import read_details
from cortex_claude.learning.extraction import Observation
from cortex_claude.learning.reading import read_file
from cortex_claude.learning.selection import feedback
from cortex_claude.learning.store import LearningStore
from cortex_claude.learning.tasks import save_task, task_detail, update_state


def preference(store, cwd, text="Use pytest for Python tests", sid="seed", explicit=True, **kwargs):
    return store.observe(Observation(text, "python.tests", "personal", "python tests", explicit=explicit, **kwargs), str(cwd), sid)["id"]


def test_selection_adds_information_and_questions_still_retrieve(tmp_path):
    with LearningStore(tmp_path / "db") as store:
        lid = preference(store, tmp_path)
        assert not store.context("Use pytest for Python tests", str(tmp_path), "prompt")["ids"]
        assert not store.context("ok", str(tmp_path), "prompt")["ids"]
        assert store.context("What should I use for Python tests?", str(tmp_path), "prompt")["ids"] == [lid]
        assert not store.context("What should I use for Python tests?", str(tmp_path), "prompt")["ids"]
        assert store.stats()["selection"]["already-in-prompt"] == 1


def test_feedback_is_idempotent_and_never_confirms_a_belief(tmp_path):
    with LearningStore(tmp_path / "db") as store:
        lid = preference(store, tmp_path)
        with pytest.raises(ValueError, match="delivered"):
            feedback(store, lid, str(tmp_path), "absent", "useful")
        for i in range(3):
            sid = f"reader{i}"
            assert store.context("Write Python tests", str(tmp_path), sid)["ids"] == [lid]
            feedback(store, lid, str(tmp_path), sid, "irrelevant", "Write Python tests")
            feedback(store, lid, str(tmp_path), sid, "irrelevant", "Write Python tests")
        assert store.list()[0]["confirmations"] == 1
        assert store.conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 3
        assert not store.context("Write Python tests", str(tmp_path), "next")["ids"]
        assert store.context("Python packaging", str(tmp_path), "different")["ids"] == [lid]


def test_conflicts_block_injection_and_details_until_human_resolution(tmp_path):
    with LearningStore(tmp_path / "db") as store:
        left = preference(store, tmp_path, explicit=False)
        right = preference(store, tmp_path, "Use unittest for Python tests", "second", explicit=False)
        conflict = list_conflicts(store)[0]
        assert not store.context("Write Python tests", str(tmp_path), "reader")["ids"]
        assert read_details(store, left, str(tmp_path), "reader")["status"] == "needs-review"
        resolve(store, conflict["id"], "keep_left" if conflict["left_id"] == right else "keep_right")
        assert not list_conflicts(store)
        assert store.context("Write Python tests", str(tmp_path), "reader")["ids"] == [right]
        with pytest.raises(ValueError, match="resolved"):
            resolve(store, conflict["id"], "keep_left")


def test_condition_resolution_preserves_default_and_exception(tmp_path):
    with LearningStore(tmp_path / "db") as store:
        normal = preference(store, tmp_path, explicit=False)
        exception = preference(store, tmp_path, "Use unittest for Python tests", "second", explicit=False)
        conflict = list_conflicts(store)[0]
        choice = "condition_left" if conflict["left_id"] == exception else "condition_right"
        result = resolve(store, conflict["id"], choice, {"all": ["legacy"]})
        assert store.context("Python tests for legacy code", str(tmp_path), delivered=False)["ids"] == [result["kept"]]
        assert store.context("Python tests", str(tmp_path), delivered=False)["ids"] == [normal]


def test_file_reads_are_fresh_bounded_and_local_to_the_receiving_session(tmp_path):
    source = tmp_path / "source.py"
    lines = [f"setting_{n} = {n}" for n in range(60)]
    source.write_text("\n".join(lines))
    with LearningStore(tmp_path / "db") as store:
        def read(sid, **kwargs):
            raw = read_file(store, str(tmp_path), "source.py", sid, max_tokens=2000, **kwargs)
            assert count_tokens(raw) <= 2000
            return json.loads(raw)
        first = read("a")
        assert first["mode"] == "full"
        assert read("a")["mode"] == "unchanged"
        lines[30] = "setting_30 = 900"
        source.write_text("\n".join(lines))
        delta = read("a")
        assert delta["mode"] == "diff" and delta["base_hash"] == first["hash"]
        assert "+setting_30 = 900" in delta["content"]
        assert read("b")["mode"] == "full"
        assert read(None)["mode"] == "full"  # Concurrent sessions are ambiguous.
        store.session("a", str(tmp_path), reset=True)
        assert read("a")["mode"] == "full"
        assert read("a", mode="full")["mode"] == "full"
        assert store.stats()["reads"]["avoided_tokens"] > 0


def test_read_cache_never_keeps_private_text_or_follows_escape_symlinks(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "secret.py").write_text("start\n<private>VERY_SECRET\n</private>\nend")
    (tmp_path / "outside").write_text("outside")
    (root / "escape").symlink_to(tmp_path / "outside")
    with LearningStore(tmp_path / "db") as store:
        response = read_file(store, str(root), "secret.py", "a")
        assert "VERY_SECRET" not in response
        cached = store.conn.execute("SELECT content FROM file_reads").fetchone()[0]
        assert "VERY_SECRET" not in cached
        with pytest.raises(ValueError, match="inside"):
            read_file(store, str(root), "escape", "a")


def test_checkpoint_resume_is_versioned_origin_bound_and_dependency_checked(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("version = 1")
    with LearningStore(tmp_path / "db") as store:
        fields = dict(title="Repair parser", summary="Parser extracted; integration pending", next_step="Wire parser into the service", decisions=["Preserve public API"], dependencies=["app.py"])
        saved = save_task(store, str(repo), "a", **fields)
        tid = saved["id"]
        assert store.context("Continue parser work", str(repo), "b")["task_id"] == tid
        assert store.context("Continue parser work", str(repo), "b")["task_id"] is None
        assert store.context("Continue parser work", str(tmp_path), "elsewhere")["task_id"] is None
        with pytest.raises(ValueError, match="expected_revision"):
            save_task(store, str(repo), "a", task_id=tid, **fields)
        updated = save_task(store, str(repo), "a", task_id=tid, expected_revision=1, **fields)
        assert updated["revision"] == 2
        assert store.context("Continue parser work", str(repo), "b")["task_id"] == tid
        (repo / "app.py").write_text("version = 2")
        assert task_detail(store, tid)["needs_review"]
        assert store.context("Continue parser work", str(repo), "c")["task_id"] is None
        with pytest.raises(ValueError, match="changed"):
            update_state(store, tid, "complete", 1)
        update_state(store, tid, "complete", 2)
        assert task_detail(store, tid)["state"] == "complete"


def test_ambiguous_resume_and_checkpoint_token_limit(tmp_path):
    with LearningStore(tmp_path / "db") as store:
        for title in ["Parser", "Database"]:
            save_task(store, str(tmp_path), "a", title=title, summary="Work in progress", next_step="Run tests")
        assert store.context("Continue", str(tmp_path), "b")["task_id"] is None
        assert store.context("Continue Parser", str(tmp_path), "b")["task_id"]
        with pytest.raises(ValueError, match="240 tokens"):
            save_task(store, str(tmp_path), "a", title="Long", summary="many details " * 500, next_step="Test")
