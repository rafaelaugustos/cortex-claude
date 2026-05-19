from __future__ import annotations

import sqlite3

import pytest

from cortex_claude.storage import migrations as M


def _build_v5_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (5);
        CREATE TABLE memories (
            id TEXT PRIMARY KEY, content TEXT NOT NULL, summary TEXT,
            tags TEXT DEFAULT '[]', scope TEXT NOT NULL,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, accessed_at INTEGER NOT NULL,
            access_count INTEGER DEFAULT 0, decay_score REAL DEFAULT 1.0
        );
        CREATE TABLE facts (
            id TEXT PRIMARY KEY, subject TEXT NOT NULL, relation TEXT NOT NULL, object TEXT NOT NULL,
            confidence REAL DEFAULT 1.0, source_memory_id TEXT NOT NULL, scope TEXT NOT NULL,
            created_at INTEGER NOT NULL, temporal TEXT, access_count INTEGER DEFAULT 0
        );
        """
    )
    return conn


class TestMigrationV6:
    def test_fresh_schema_has_cluster_columns(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(M.SCHEMA_SQL)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()]
        assert "cluster_id" in cols

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "clusters" in tables

    def test_migrates_from_v5(self):
        conn = _build_v5_db()
        conn.execute(
            "INSERT INTO memories VALUES ('m1', 'hi', NULL, '[]', 'global', 1, 1, 1, 0, 1.0)"
        )
        M._migrate_to_v6(conn)

        v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == 6

        cols = [r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()]
        assert "cluster_id" in cols

        # data preserved with NULL cluster_id
        row = conn.execute("SELECT id, cluster_id FROM memories").fetchone()
        assert row[0] == "m1"
        assert row[1] is None

    def test_migration_is_idempotent(self):
        conn = _build_v5_db()
        M._migrate_to_v6(conn)
        # Second run should not raise
        M._migrate_to_v6(conn)
        v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == 6

    def test_cluster_index_created(self):
        conn = _build_v5_db()
        M._migrate_to_v6(conn)
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        assert "idx_memories_cluster" in idx
        assert "idx_clusters_scope" in idx
