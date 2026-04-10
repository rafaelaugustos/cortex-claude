from __future__ import annotations

import sqlite3

from cortex_claude.models.fact import Fact


class FactRepository:
    def save(self, conn: sqlite3.Connection, fact: Fact) -> str:
        conn.execute(
            """
            INSERT INTO facts (id, subject, relation, object, confidence, source_memory_id, scope, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact.id,
                fact.subject,
                fact.relation,
                fact.object,
                fact.confidence,
                fact.source_memory_id,
                fact.scope,
                fact.created_at,
            ),
        )
        conn.commit()
        return fact.id

    def save_batch(self, conn: sqlite3.Connection, facts: list[Fact]) -> int:
        conn.executemany(
            """
            INSERT INTO facts (id, subject, relation, object, confidence, source_memory_id, scope, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (f.id, f.subject, f.relation, f.object, f.confidence, f.source_memory_id, f.scope, f.created_at)
                for f in facts
            ],
        )
        conn.commit()
        return len(facts)

    def search(
        self,
        conn: sqlite3.Connection,
        topic: str,
        relation: str | None = None,
        limit: int = 20,
    ) -> list[Fact]:
        topic_lower = f"%{topic.lower()}%"

        if relation:
            rows = conn.execute(
                """
                SELECT * FROM facts
                WHERE (LOWER(subject) LIKE ? OR LOWER(object) LIKE ?)
                AND LOWER(relation) = ?
                ORDER BY confidence DESC
                LIMIT ?
                """,
                (topic_lower, topic_lower, relation.lower(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM facts
                WHERE LOWER(subject) LIKE ? OR LOWER(object) LIKE ?
                ORDER BY confidence DESC
                LIMIT ?
                """,
                (topic_lower, topic_lower, limit),
            ).fetchall()

        return [
            Fact(
                id=row["id"],
                subject=row["subject"],
                relation=row["relation"],
                object=row["object"],
                confidence=row["confidence"],
                source_memory_id=row["source_memory_id"],
                scope=row["scope"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def search_by_memory(self, conn: sqlite3.Connection, memory_id: str) -> list[Fact]:
        rows = conn.execute(
            "SELECT * FROM facts WHERE source_memory_id = ? ORDER BY confidence DESC",
            (memory_id,),
        ).fetchall()

        return [
            Fact(
                id=row["id"],
                subject=row["subject"],
                relation=row["relation"],
                object=row["object"],
                confidence=row["confidence"],
                source_memory_id=row["source_memory_id"],
                scope=row["scope"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete_by_memory(self, conn: sqlite3.Connection, memory_id: str) -> int:
        cursor = conn.execute(
            "DELETE FROM facts WHERE source_memory_id = ?", (memory_id,)
        )
        conn.commit()
        return cursor.rowcount

    def count(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COUNT(*) FROM facts").fetchone()
        return row[0]
