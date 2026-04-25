from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 5

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    summary TEXT,
    tags TEXT DEFAULT '[]',
    scope TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    accessed_at INTEGER NOT NULL,
    access_count INTEGER DEFAULT 0,
    decay_score REAL DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_memories_accessed ON memories(accessed_at);
CREATE INDEX IF NOT EXISTS idx_memories_decay ON memories(decay_score);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    relation TEXT NOT NULL,
    object TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    source_memory_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    temporal TEXT,
    access_count INTEGER DEFAULT 0,
    FOREIGN KEY (source_memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
CREATE INDEX IF NOT EXISTS idx_facts_object ON facts(object);
CREATE INDEX IF NOT EXISTS idx_facts_relation ON facts(relation);
CREATE INDEX IF NOT EXISTS idx_facts_subject_relation ON facts(subject, relation);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    summary,
    tags,
    content='memories',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, summary, tags)
    VALUES (new.rowid, new.content, new.summary, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, summary, tags)
    VALUES ('delete', old.rowid, old.content, old.summary, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, summary, tags)
    VALUES ('delete', old.rowid, old.content, old.summary, old.tags);
    INSERT INTO memories_fts(rowid, content, summary, tags)
    VALUES (new.rowid, new.content, new.summary, new.tags);
END;
"""


def _vector_table_sql(dim: int) -> str:
    return f"""
CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0(
    id TEXT PRIMARY KEY,
    embedding float[{dim}]
);
"""


def initialize_schema(conn: sqlite3.Connection, embedding_dim: int = 384) -> None:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    row = cursor.fetchone()

    if row is not None:
        version = conn.execute("SELECT version FROM schema_version").fetchone()
        current = version[0] if version else 0
        if current < 2:
            _migrate_to_v2(conn)
        if current < 3:
            _migrate_to_v3(conn, embedding_dim)
        if current < 4:
            _migrate_to_v4(conn)
        if current < 5:
            _migrate_to_v5(conn)
        return

    conn.executescript(SCHEMA_SQL)
    conn.execute(_vector_table_sql(embedding_dim))
    conn.executescript(FTS_SQL)
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('embedding_dim', ?)",
        (str(embedding_dim),),
    )
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    fts_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memories_fts'"
    ).fetchone()

    if not fts_exists:
        conn.executescript(FTS_SQL)
        conn.execute(
            """
            INSERT INTO memories_fts(rowid, content, summary, tags)
            SELECT rowid, content, summary, tags FROM memories
            """
        )

    conn.execute("UPDATE schema_version SET version = 2")
    conn.commit()


def _migrate_to_v3(conn: sqlite3.Connection, embedding_dim: int) -> None:
    meta_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()

    if not meta_exists:
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('embedding_dim', ?)",
        (str(embedding_dim),),
    )
    conn.execute("UPDATE schema_version SET version = 3")
    conn.commit()


def _migrate_to_v4(conn: sqlite3.Connection) -> None:
    columns = [row[1] for row in conn.execute("PRAGMA table_info(facts)").fetchall()]
    if "temporal" not in columns:
        conn.execute("ALTER TABLE facts ADD COLUMN temporal TEXT")

    conn.execute("UPDATE schema_version SET version = 4")
    conn.commit()


def _migrate_to_v5(conn: sqlite3.Connection) -> None:
    columns = [row[1] for row in conn.execute("PRAGMA table_info(facts)").fetchall()]
    if "access_count" not in columns:
        conn.execute("ALTER TABLE facts ADD COLUMN access_count INTEGER DEFAULT 0")

    conn.execute("UPDATE schema_version SET version = 5")
    conn.commit()
