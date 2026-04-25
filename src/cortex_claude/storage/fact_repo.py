from __future__ import annotations

import sqlite3

from cortex_claude.models.fact import Fact


class FactRepository:
    def save(self, conn: sqlite3.Connection, fact: Fact) -> str:
        existing = self._find_duplicate(conn, fact)
        if existing:
            new_confidence = min(existing["confidence"] + 0.1, 1.0)
            conn.execute(
                "UPDATE facts SET confidence = ?, source_memory_id = ?, created_at = ? WHERE id = ?",
                (new_confidence, fact.source_memory_id, fact.created_at, existing["id"]),
            )
            conn.commit()
            return existing["id"]

        conn.execute(
            """
            INSERT INTO facts (id, subject, relation, object, confidence, source_memory_id, scope, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fact.id, fact.subject, fact.relation, fact.object, fact.confidence, fact.source_memory_id, fact.scope, fact.created_at),
        )
        conn.commit()
        return fact.id

    def save_batch(self, conn: sqlite3.Connection, facts: list[Fact]) -> int:
        saved = 0
        for fact in facts:
            existing = self._find_duplicate(conn, fact)
            if existing:
                new_confidence = min(existing["confidence"] + 0.1, 1.0)
                conn.execute(
                    "UPDATE facts SET confidence = ?, source_memory_id = ?, created_at = ? WHERE id = ?",
                    (new_confidence, fact.source_memory_id, fact.created_at, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO facts (id, subject, relation, object, confidence, source_memory_id, scope, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (fact.id, fact.subject, fact.relation, fact.object, fact.confidence, fact.source_memory_id, fact.scope, fact.created_at),
                )
                saved += 1
        conn.commit()
        return saved

    def _find_duplicate(self, conn: sqlite3.Connection, fact: Fact) -> dict | None:
        row = conn.execute(
            "SELECT id, confidence FROM facts WHERE LOWER(subject) = ? AND LOWER(relation) = ? AND LOWER(object) = ?",
            (fact.subject.lower(), fact.relation.lower(), fact.object.lower()),
        ).fetchone()
        if row:
            return {"id": row["id"], "confidence": row["confidence"]}
        return None

    def consolidate(self, conn: sqlite3.Connection) -> int:
        rows = conn.execute(
            """
            SELECT LOWER(subject) as subj, LOWER(relation) as rel, LOWER(object) as obj,
                   COUNT(*) as cnt, MAX(confidence) as max_conf, MAX(created_at) as latest
            FROM facts
            GROUP BY LOWER(subject), LOWER(relation), LOWER(object)
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        merged = 0
        for row in rows:
            duplicates = conn.execute(
                """
                SELECT id, confidence, source_memory_id, scope, created_at
                FROM facts
                WHERE LOWER(subject) = ? AND LOWER(relation) = ? AND LOWER(object) = ?
                ORDER BY confidence DESC, created_at DESC
                """,
                (row["subj"], row["rel"], row["obj"]),
            ).fetchall()

            if len(duplicates) <= 1:
                continue

            keeper = duplicates[0]
            boost = min(len(duplicates) * 0.05, 0.3)
            new_confidence = min(keeper["confidence"] + boost, 1.0)

            conn.execute(
                "UPDATE facts SET confidence = ? WHERE id = ?",
                (new_confidence, keeper["id"]),
            )

            for dup in duplicates[1:]:
                conn.execute("DELETE FROM facts WHERE id = ?", (dup["id"],))
                merged += 1

        conn.commit()
        return merged

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

        return [self._row_to_fact(row) for row in rows]

    def search_by_memory(self, conn: sqlite3.Connection, memory_id: str) -> list[Fact]:
        rows = conn.execute(
            "SELECT * FROM facts WHERE source_memory_id = ? ORDER BY confidence DESC",
            (memory_id,),
        ).fetchall()
        return [self._row_to_fact(row) for row in rows]

    def delete_by_memory(self, conn: sqlite3.Connection, memory_id: str) -> int:
        cursor = conn.execute(
            "DELETE FROM facts WHERE source_memory_id = ?", (memory_id,)
        )
        conn.commit()
        return cursor.rowcount

    def count(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COUNT(*) FROM facts").fetchone()
        return row[0]

    def _row_to_fact(self, row) -> Fact:
        return Fact(
            id=row["id"],
            subject=row["subject"],
            relation=row["relation"],
            object=row["object"],
            confidence=row["confidence"],
            source_memory_id=row["source_memory_id"],
            scope=row["scope"],
            created_at=row["created_at"],
        )
