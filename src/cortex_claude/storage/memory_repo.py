from __future__ import annotations

import json
import sqlite3
import time

import numpy as np

from cortex_claude.models.memory import Memory


class MemoryRepository:
    def save(self, conn: sqlite3.Connection, memory: Memory, embedding: np.ndarray) -> str:
        conn.execute(
            """
            INSERT INTO memories (id, content, summary, tags, scope, created_at, updated_at, accessed_at, access_count, decay_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.content,
                memory.summary,
                json.dumps(memory.tags),
                memory.scope,
                memory.created_at,
                memory.updated_at,
                memory.accessed_at,
                memory.access_count,
                memory.decay_score,
            ),
        )

        embedding_blob = embedding.astype(np.float32).tobytes()
        conn.execute(
            "INSERT INTO memory_vectors (id, embedding) VALUES (?, ?)",
            (memory.id, embedding_blob),
        )

        conn.commit()
        return memory.id

    def get(self, conn: sqlite3.Connection, memory_id: str) -> Memory | None:
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()

        if row is None:
            return None

        return Memory(
            id=row["id"],
            content=row["content"],
            summary=row["summary"],
            tags=json.loads(row["tags"]),
            scope=row["scope"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            accessed_at=row["accessed_at"],
            access_count=row["access_count"],
            decay_score=row["decay_score"],
        )

    def search_by_vector(
        self,
        conn: sqlite3.Connection,
        embedding: np.ndarray,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        embedding_blob = embedding.astype(np.float32).tobytes()
        rows = conn.execute(
            """
            SELECT id, distance
            FROM memory_vectors
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (embedding_blob, limit),
        ).fetchall()

        return [(row[0], 1.0 - (row[1] ** 2) / 2.0) for row in rows]

    def update_accessed(self, conn: sqlite3.Connection, memory_id: str) -> None:
        now = int(time.time() * 1000)
        conn.execute(
            """
            UPDATE memories
            SET accessed_at = ?, access_count = access_count + 1
            WHERE id = ?
            """,
            (now, memory_id),
        )
        conn.commit()

    def delete(self, conn: sqlite3.Connection, memory_id: str) -> None:
        conn.execute("DELETE FROM memory_vectors WHERE id = ?", (memory_id,))
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()

    def search_fts(
        self,
        conn: sqlite3.Connection,
        query: str,
        limit: int = 10,
    ) -> list[str]:
        try:
            rows = conn.execute(
                """
                SELECT m.id
                FROM memories_fts f
                JOIN memories m ON m.rowid = f.rowid
                WHERE memories_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
            return [row[0] for row in rows]
        except Exception:
            return []

    def search_by_query(
        self,
        conn: sqlite3.Connection,
        query: str,
        limit: int = 10,
    ) -> list[Memory]:
        ids = self.search_fts(conn, query, limit)
        memories = []
        for mid in ids:
            m = self.get(conn, mid)
            if m:
                memories.append(m)
        return memories

    def count(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return row[0]

    def get_all_ids(self, conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute("SELECT id FROM memories").fetchall()
        return [row[0] for row in rows]
