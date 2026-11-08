"""Transactional, additive upgrades of the shared memory database."""
from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        version = conn.execute("SELECT value FROM learning_meta WHERE key='schema_version'").fetchone()[0]
        if version not in {"1", "2", "3", "4", "5"}:
            raise ValueError("Unsupported learning database version")
        if version == "1":
            for column in (
                "kind TEXT NOT NULL DEFAULT 'preference'",
                "conditions TEXT NOT NULL DEFAULT '{}'",
                "details TEXT NOT NULL DEFAULT '{}'",
                "dependencies TEXT NOT NULL DEFAULT '{}'",
                "dependency_origin TEXT NOT NULL DEFAULT ''",
                "expires_at REAL",
                "validation TEXT NOT NULL DEFAULT 'not-required'",
                "stale_reason TEXT NOT NULL DEFAULT ''",
            ):
                conn.execute(f"ALTER TABLE lessons ADD COLUMN {column}")
            conn.execute("ALTER TABLE sessions ADD COLUMN detail_tokens INTEGER NOT NULL DEFAULT 0")
            conn.execute("UPDATE learning_meta SET value='2' WHERE key='schema_version'")
        for sql in (
            "CREATE TABLE IF NOT EXISTS lesson_vectors (lesson_id TEXT PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE, model TEXT NOT NULL, vector TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS detail_deliveries (session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE, tokens INTEGER NOT NULL, PRIMARY KEY(session_id,lesson_id))",
            "CREATE TABLE IF NOT EXISTS verifications (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, origin TEXT NOT NULL, command TEXT NOT NULL, passed INTEGER NOT NULL, observed_at REAL NOT NULL)",
            "CREATE TABLE IF NOT EXISTS outcomes (lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE, session_id TEXT NOT NULL, origin TEXT NOT NULL, outcome TEXT NOT NULL, verification_id TEXT, observed_at REAL NOT NULL, PRIMARY KEY(lesson_id,session_id))",
            "CREATE TABLE IF NOT EXISTS usage_messages (session_id TEXT NOT NULL, message_id TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, cache_read_tokens INTEGER NOT NULL, cache_creation_tokens INTEGER NOT NULL, PRIMARY KEY(session_id,message_id))",
            "CREATE TABLE IF NOT EXISTS transcript_offsets (session_id TEXT NOT NULL, path TEXT NOT NULL, file_id TEXT NOT NULL, offset INTEGER NOT NULL, PRIMARY KEY(session_id,path))",
            "CREATE TABLE IF NOT EXISTS task_runs (id TEXT PRIMARY KEY, task TEXT NOT NULL, variant TEXT NOT NULL, model TEXT NOT NULL, quality REAL NOT NULL, elapsed_ms REAL NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, cache_read_tokens INTEGER NOT NULL, cache_creation_tokens INTEGER NOT NULL, tool_calls INTEGER NOT NULL, failures INTEGER NOT NULL, cost_usd REAL, created_at REAL NOT NULL)",
        ):
            conn.execute(sql)
        if "skipping" not in {r[1] for r in conn.execute("PRAGMA table_info(transcript_offsets)")}:
            conn.execute("ALTER TABLE transcript_offsets ADD COLUMN skipping INTEGER NOT NULL DEFAULT 0")
        for sql in (
            "CREATE TABLE IF NOT EXISTS feedback (lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE, session_id TEXT NOT NULL, origin TEXT NOT NULL, assessment TEXT NOT NULL CHECK(assessment IN ('useful','irrelevant','corrected')), task_terms TEXT NOT NULL, source TEXT NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(lesson_id,session_id))",
            "CREATE TABLE IF NOT EXISTS selection_events (session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE, reason TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(session_id,lesson_id,reason))",
            "CREATE TABLE IF NOT EXISTS conflicts (id TEXT PRIMARY KEY, left_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE, right_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE, reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open', resolution TEXT, created_at REAL NOT NULL, resolved_at REAL, UNIQUE(left_id,right_id))",
            "CREATE TABLE IF NOT EXISTS work_items (id TEXT PRIMARY KEY, origin TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL, decisions TEXT NOT NULL, pending TEXT NOT NULL, next_step TEXT NOT NULL, dependencies TEXT NOT NULL, revision INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'open', session_id TEXT NOT NULL, updated_at REAL NOT NULL, expires_at REAL NOT NULL)",
            "CREATE TABLE IF NOT EXISTS task_deliveries (session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, task_id TEXT NOT NULL REFERENCES work_items(id) ON DELETE CASCADE, revision INTEGER NOT NULL, PRIMARY KEY(session_id,task_id))",
            "CREATE TABLE IF NOT EXISTS file_reads (session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, origin TEXT NOT NULL, path TEXT NOT NULL, range_key TEXT NOT NULL, digest TEXT NOT NULL, content TEXT NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(session_id,origin,path,range_key))",
            "CREATE TABLE IF NOT EXISTS read_metrics (session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE, full_reads INTEGER NOT NULL DEFAULT 0, delta_reads INTEGER NOT NULL DEFAULT 0, unchanged_reads INTEGER NOT NULL DEFAULT 0, emitted_tokens INTEGER NOT NULL DEFAULT 0, avoided_tokens INTEGER NOT NULL DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS project_profiles (origin TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL, sources TEXT NOT NULL, revision INTEGER NOT NULL, updated_at REAL NOT NULL)",
            "CREATE TABLE IF NOT EXISTS project_notes (id TEXT PRIMARY KEY, origin TEXT NOT NULL REFERENCES project_profiles(origin) ON DELETE CASCADE, section TEXT NOT NULL, content TEXT NOT NULL, sources TEXT NOT NULL, updated_at REAL NOT NULL)",
            "CREATE TABLE IF NOT EXISTS project_deliveries (session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, origin TEXT NOT NULL REFERENCES project_profiles(origin) ON DELETE CASCADE, revision INTEGER NOT NULL, PRIMARY KEY(session_id,origin))",
            "CREATE TABLE IF NOT EXISTS automatic_checkpoints (session_id TEXT NOT NULL, origin TEXT NOT NULL, client TEXT NOT NULL, task_id TEXT NOT NULL, goal TEXT NOT NULL, last_message TEXT NOT NULL, files TEXT NOT NULL, event_at REAL NOT NULL, event_id TEXT NOT NULL, PRIMARY KEY(session_id,origin))",
            "CREATE TABLE IF NOT EXISTS durable_writes (id INTEGER PRIMARY KEY CHECK(id=1), saved_at REAL NOT NULL, kind TEXT NOT NULL)",
        ):
            conn.execute(sql)
        conn.execute("INSERT OR IGNORE INTO durable_writes VALUES (1,0,'none')")
        for table in ('lessons', 'project_profiles', 'project_notes', 'work_items'):
            for event in ('INSERT', 'UPDATE', 'DELETE'):
                conn.execute(f"CREATE TRIGGER IF NOT EXISTS audit_{table}_{event.lower()} AFTER {event} ON {table} BEGIN UPDATE durable_writes SET saved_at=(julianday('now')-2440587.5)*86400,kind='{table}' WHERE id=1; END")
        conn.execute("UPDATE learning_meta SET value='5' WHERE key='schema_version'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
