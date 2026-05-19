from __future__ import annotations

import sqlite3

import pytest

from cortex_claude.storage import migrations as M


def _build_v6_db() -> sqlite3.Connection:
    """Build a v6-shaped db with facts.source_memory_id NOT NULL."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (6);
        CREATE TABLE memories (
            id TEXT PRIMARY KEY, content TEXT NOT NULL, summary TEXT,
            tags TEXT DEFAULT '[]', scope TEXT NOT NULL,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, accessed_at INTEGER NOT NULL,
            access_count INTEGER DEFAULT 0, decay_score REAL DEFAULT 1.0,
            cluster_id INTEGER
        );
        CREATE TABLE facts (
            id TEXT PRIMARY KEY, subject TEXT NOT NULL, relation TEXT NOT NULL, object TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source_memory_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            created_at INTEGER NOT NULL, temporal TEXT, access_count INTEGER DEFAULT 0,
            FOREIGN KEY (source_memory_id) REFERENCES memories(id) ON DELETE CASCADE
        );
        CREATE TABLE clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL, label TEXT, centroid BLOB,
            member_count INTEGER DEFAULT 0, updated_at INTEGER NOT NULL
        );
        """
    )
    # Seed a fact with a non-null source_memory_id
    conn.execute(
        "INSERT INTO memories (id, content, scope, created_at, updated_at, accessed_at) VALUES (?,?,?,?,?,?)",
        ("m1", "hi", "global", 1, 1, 1),
    )
    conn.execute(
        "INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("f1", "subj", "rel", "obj", 1.0, "m1", "global", 1, None, 0),
    )
    conn.commit()
    return conn


class TestMigrationV7:
    def test_makes_source_memory_id_nullable(self):
        conn = _build_v6_db()
        M._migrate_to_v7(conn)

        v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == 7

        # Now inserting a fact with NULL source_memory_id must succeed
        conn.execute(
            "INSERT INTO facts (id, subject, relation, object, confidence, source_memory_id, scope, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("f2", "code_func", "defined_in", "/a.py:1", 0.95, None, "global", 1),
        )
        conn.commit()

        row = conn.execute("SELECT source_memory_id FROM facts WHERE id = 'f2'").fetchone()
        assert row[0] is None

    def test_preserves_existing_facts(self):
        conn = _build_v6_db()
        M._migrate_to_v7(conn)
        row = conn.execute("SELECT subject, source_memory_id FROM facts WHERE id = 'f1'").fetchone()
        assert row[0] == "subj"
        assert row[1] == "m1"

    def test_is_idempotent(self):
        conn = _build_v6_db()
        M._migrate_to_v7(conn)
        # Second run is a no-op
        M._migrate_to_v7(conn)
        v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == 7

    def test_fresh_schema_has_nullable_source(self):
        """A fresh init via SCHEMA_SQL must produce a nullable source_memory_id."""
        conn = sqlite3.connect(":memory:")
        conn.executescript(M.SCHEMA_SQL)
        info = conn.execute("PRAGMA table_info(facts)").fetchall()
        source_col = next(c for c in info if c[1] == "source_memory_id")
        notnull_flag = source_col[3]
        assert notnull_flag == 0
