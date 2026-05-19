from __future__ import annotations

import sqlite3

import pytest

from cortex_claude.code.extractor import Symbol
from cortex_claude.code.facts import (
    CODE_FACT_CONFIDENCE,
    known_symbol_names,
    mention_facts,
    symbols_to_facts,
)
from cortex_claude.storage import migrations as M


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


class TestSymbolsToFacts:
    def test_function_emits_defined_in_and_language(self):
        sym = Symbol(name="hello", kind="function", line=10, language="python", path="/a.py")
        facts = symbols_to_facts([sym])
        relations = {(f.subject, f.relation, f.object) for f in facts}
        assert ("hello", "defined_in", "/a.py:10") in relations
        assert ("hello", "in_language", "python") in relations

    def test_calls_emit_one_fact_each(self):
        sym = Symbol(
            name="f", kind="function", line=1, language="python", path="/a.py",
            calls=["g", "h"],
        )
        facts = symbols_to_facts([sym])
        calls = [(f.subject, f.object) for f in facts if f.relation == "calls"]
        assert ("f", "g") in calls
        assert ("f", "h") in calls

    def test_extends_relation(self):
        sym = Symbol(
            name="Foo", kind="class", line=1, language="python", path="/a.py",
            extends=["Bar"],
        )
        facts = symbols_to_facts([sym])
        assert any(f.relation == "extends" and f.object == "Bar" for f in facts)

    def test_imports_relation(self):
        sym = Symbol(
            name="mod", kind="module", line=1, language="python", path="/a.py",
            imports=["json"],
        )
        facts = symbols_to_facts([sym])
        assert any(f.relation == "imports" and f.object == "json" for f in facts)

    def test_facts_have_no_source_memory_id(self):
        sym = Symbol(name="f", kind="function", line=1, language="python", path="/a.py")
        facts = symbols_to_facts([sym])
        assert all(f.source_memory_id is None for f in facts)

    def test_facts_have_high_confidence(self):
        sym = Symbol(name="f", kind="function", line=1, language="python", path="/a.py")
        facts = symbols_to_facts([sym])
        assert all(f.confidence == CODE_FACT_CONFIDENCE for f in facts)


class TestKnownSymbolNames:
    def test_returns_subjects_with_defined_in(self, db: sqlite3.Connection):
        db.executemany(
            "INSERT INTO facts (id, subject, relation, object, scope, created_at) VALUES (?,?,?,?,?,?)",
            [
                ("1", "foo", "defined_in", "/a.py:1", "global", 0),
                ("2", "Bar", "defined_in", "/b.py:1", "global", 0),
                ("3", "baz", "mentions", "x", "global", 0),  # not a code symbol
                ("4", "qux", "defined_in", "/c.py:1", "other", 0),  # different scope
            ],
        )
        db.commit()
        names = known_symbol_names(db, "global")
        assert names == {"foo", "Bar"}


class TestMentionFacts:
    def test_extracts_symbols_mentioned_in_text(self):
        known = {"my_func", "MyClass"}
        content = "I think my_func() is broken, MyClass is fine though"
        facts = mention_facts("mem-1", content, known, "global")
        objects = {f.object for f in facts}
        assert objects == {"my_func", "MyClass"}
        assert all(f.relation == "mentions" for f in facts)
        assert all(f.subject == "memory:mem-1" for f in facts)

    def test_no_match_returns_empty(self):
        facts = mention_facts("m", "totally unrelated text", {"foo", "bar"}, "global")
        assert facts == []

    def test_empty_known_returns_empty(self):
        assert mention_facts("m", "anything", set(), "global") == []

    def test_short_tokens_ignored(self):
        """The regex requires 3+ chars to avoid matching every 'a' or 'in'."""
        known = {"go"}
        facts = mention_facts("m", "go here", known, "global")
        assert facts == []  # 'go' is only 2 chars, won't be tokenized
