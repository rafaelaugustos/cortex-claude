from __future__ import annotations

import sqlite3

import pytest

from cortex_claude.models.fact import Fact
from cortex_claude.storage import migrations as M
from cortex_claude.storage.fact_repo import FactRepository


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(M.SCHEMA_SQL)
    conn.executescript(M.FTS_SQL)
    conn.execute("CREATE TABLE memory_vectors (id TEXT PRIMARY KEY, embedding BLOB)")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (M.SCHEMA_VERSION,))
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def repo() -> FactRepository:
    return FactRepository()


class TestDetectContradictions:
    def test_flags_conflicting_is_relation(self, db, repo):
        repo.save(db, Fact(subject="db", relation="is", object="postgres", scope="global"))
        new_fact = Fact(subject="db", relation="is", object="mysql", scope="global")
        contradictions = repo.detect_contradictions(db, new_fact, "global")
        assert len(contradictions) == 1
        assert contradictions[0].object == "postgres"

    @pytest.mark.parametrize("relation", ["runs_on", "located_in", "written_in"])
    def test_does_not_flag_legitimately_coexisting_relations(self, db, repo, relation):
        """runs_on/located_in/written_in were removed from EXCLUSIVE_RELATIONS:
        an entity can run on / be located in / be written in more than one
        thing at once (multi-region deploy, polyglot project), so a second
        fact with a different object is not a contradiction."""
        repo.save(db, Fact(subject="api", relation=relation, object="staging", scope="global"))
        new_fact = Fact(subject="api", relation=relation, object="production", scope="global")
        assert repo.detect_contradictions(db, new_fact, "global") == []

    def test_scoped_to_the_given_scope(self, db, repo):
        repo.save(db, Fact(subject="db", relation="is", object="postgres", scope="project:a"))
        new_fact = Fact(subject="db", relation="is", object="mysql", scope="project:b")
        assert repo.detect_contradictions(db, new_fact, "project:b") == []


class TestFindDuplicateScoped:
    def test_duplicate_in_same_scope_is_merged(self, db, repo):
        f1 = Fact(subject="x", relation="uses", object="y", scope="global", confidence=0.6)
        repo.save(db, f1)
        f2 = Fact(subject="x", relation="uses", object="y", scope="global", confidence=0.6)
        repo.save(db, f2)
        assert repo.count(db) == 1

    def test_same_triplet_different_scope_is_not_merged(self, db, repo):
        f1 = Fact(subject="x", relation="uses", object="y", scope="project:a")
        repo.save(db, f1)
        f2 = Fact(subject="x", relation="uses", object="y", scope="project:b")
        repo.save(db, f2)
        assert repo.count(db) == 2


class TestSearchScoped:
    def test_search_filters_by_scope(self, db, repo):
        repo.save(db, Fact(subject="widget", relation="uses", object="react", scope="project:a"))
        repo.save(db, Fact(subject="widget", relation="uses", object="vue", scope="project:b"))

        results = repo.search(db, "widget", scope="project:a")
        assert len(results) == 1
        assert results[0].object == "react"

    def test_search_without_scope_returns_all(self, db, repo):
        repo.save(db, Fact(subject="widget", relation="uses", object="react", scope="project:a"))
        repo.save(db, Fact(subject="widget", relation="uses", object="vue", scope="project:b"))

        results = repo.search(db, "widget")
        assert len(results) == 2


class TestDeleteBySourceFile:
    def test_removes_all_facts_for_symbols_defined_in_file(self, db, repo):
        repo.save_batch(db, [
            Fact(subject="foo", relation="defined_in", object="/a.py:1", scope="global", source_memory_id=None),
            Fact(subject="foo", relation="in_language", object="python", scope="global", source_memory_id=None),
            Fact(subject="foo", relation="calls", object="bar", scope="global", source_memory_id=None),
            Fact(subject="other", relation="defined_in", object="/b.py:1", scope="global", source_memory_id=None),
        ])
        assert repo.count(db) == 4

        deleted = repo.delete_by_source_file(db, "global", "/a.py")
        assert deleted == 3
        assert repo.count(db) == 1
        remaining = repo.search(db, "other", scope="global")
        assert len(remaining) == 1

    def test_no_symbols_in_file_returns_zero(self, db, repo):
        assert repo.delete_by_source_file(db, "global", "/nonexistent.py") == 0

    def test_scoped_to_given_scope(self, db, repo):
        repo.save_batch(db, [
            Fact(subject="foo", relation="defined_in", object="/a.py:1", scope="project:a", source_memory_id=None),
        ])
        assert repo.delete_by_source_file(db, "project:b", "/a.py") == 0
        assert repo.count(db) == 1

    def test_removes_calls_from_facts_qualified_by_path(self, db, repo):
        """calls_from facts use a `path:name` subject (not a bare symbol
        name), so they need their own cleanup path distinct from the
        defined_in-based one used for calls/imports/extends."""
        repo.save_batch(db, [
            Fact(subject="foo", relation="defined_in", object="/a.py:1", scope="global", source_memory_id=None),
            Fact(subject="/a.py:foo", relation="calls_from", object="mod:bar", scope="global", source_memory_id=None),
            Fact(subject="/b.py:other", relation="calls_from", object="mod:bar", scope="global", source_memory_id=None),
        ])
        assert repo.count(db) == 3

        deleted = repo.delete_by_source_file(db, "global", "/a.py")
        assert deleted == 2
        assert repo.count(db) == 1
        remaining = repo.search(db, "other", scope="global")
        assert len(remaining) == 1
