from __future__ import annotations

import sqlite3

from cortex_claude.models.fact import Fact


class FactRepository:
    def save(self, conn: sqlite3.Connection, fact: Fact) -> str:
        existing = self._find_duplicate(conn, fact, fact.scope)
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
            INSERT INTO facts (id, subject, relation, object, confidence, source_memory_id, scope, created_at, temporal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fact.id, fact.subject, fact.relation, fact.object, fact.confidence, fact.source_memory_id, fact.scope, fact.created_at, fact.temporal),
        )
        conn.commit()
        return fact.id

    def save_batch(self, conn: sqlite3.Connection, facts: list[Fact]) -> int:
        saved = 0
        for fact in facts:
            existing = self._find_duplicate(conn, fact, fact.scope)
            if existing:
                new_confidence = min(existing["confidence"] + 0.1, 1.0)
                temporal = fact.temporal or existing.get("temporal")
                conn.execute(
                    "UPDATE facts SET confidence = ?, source_memory_id = ?, created_at = ?, temporal = COALESCE(?, temporal) WHERE id = ?",
                    (new_confidence, fact.source_memory_id, fact.created_at, temporal, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO facts (id, subject, relation, object, confidence, source_memory_id, scope, created_at, temporal)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (fact.id, fact.subject, fact.relation, fact.object, fact.confidence, fact.source_memory_id, fact.scope, fact.created_at, fact.temporal),
                )
                saved += 1
        conn.commit()
        return saved

    def _find_duplicate(self, conn: sqlite3.Connection, fact: Fact, scope: str) -> dict | None:
        row = conn.execute(
            "SELECT id, confidence, temporal FROM facts WHERE LOWER(subject) = ? AND LOWER(relation) = ? AND LOWER(object) = ? AND scope = ?",
            (fact.subject.lower(), fact.relation.lower(), fact.object.lower(), scope),
        ).fetchone()
        if row:
            return {"id": row["id"], "confidence": row["confidence"], "temporal": row["temporal"]}
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
        scope: str | None = None,
    ) -> list[Fact]:
        topic_lower = f"%{topic.lower()}%"

        if relation and scope:
            rows = conn.execute(
                """
                SELECT * FROM facts
                WHERE (LOWER(subject) LIKE ? OR LOWER(object) LIKE ?)
                AND LOWER(relation) = ? AND scope = ?
                ORDER BY confidence DESC
                LIMIT ?
                """,
                (topic_lower, topic_lower, relation.lower(), scope, limit),
            ).fetchall()
        elif relation:
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
        elif scope:
            rows = conn.execute(
                """
                SELECT * FROM facts
                WHERE (LOWER(subject) LIKE ? OR LOWER(object) LIKE ?) AND scope = ?
                ORDER BY confidence DESC
                LIMIT ?
                """,
                (topic_lower, topic_lower, scope, limit),
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

    def delete_by_source_file(self, conn: sqlite3.Connection, scope: str, path: str) -> int:
        """Delete all code-graph facts for symbols defined in `path`.

        Code facts have source_memory_id=NULL, so the only way to identify
        "facts belonging to this file" is via the `defined_in` relation,
        whose object is `path:line`. We first find the symbol names
        (subjects) defined in this file, then delete every fact about those
        subjects in this scope (defined_in, in_language, calls, extends,
        imports) so re-indexing an edited file doesn't accumulate stale facts
        for removed/renamed symbols.
        """
        subjects = conn.execute(
            "SELECT DISTINCT subject FROM facts WHERE scope = ? AND relation = 'defined_in' AND object LIKE ?",
            (scope, f"{path}:%"),
        ).fetchall()
        subject_names = [row[0] for row in subjects]
        if not subject_names:
            return 0

        placeholders = ",".join("?" for _ in subject_names)
        cursor = conn.execute(
            f"DELETE FROM facts WHERE scope = ? AND subject IN ({placeholders})",
            (scope, *subject_names),
        )
        conn.commit()
        return cursor.rowcount

    def count(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COUNT(*) FROM facts").fetchone()
        return row[0]

    def boost_accessed(self, conn: sqlite3.Connection, fact_ids: list[str], amount: float = 0.02) -> None:
        for fid in fact_ids:
            conn.execute(
                "UPDATE facts SET access_count = access_count + 1, confidence = MIN(confidence + ?, 1.0) WHERE id = ?",
                (amount, fid),
            )
        conn.commit()

    # Only relations that are genuinely 1-to-1 by nature. Relations like
    # "runs_on"/"located_in"/"written_in" were removed: an entity can
    # legitimately run on / be located in / be written in multiple things
    # at once (multi-region deploy, polyglot project), so treating a new
    # object as a contradiction of an old one there was penalizing valid,
    # coexisting facts.
    EXCLUSIVE_RELATIONS = {"be", "is", "defaults_to", "has_value"}

    def detect_contradictions(self, conn: sqlite3.Connection, fact: Fact, scope: str) -> list[Fact]:
        if fact.relation.lower() not in self.EXCLUSIVE_RELATIONS:
            return []

        rows = conn.execute(
            """
            SELECT * FROM facts
            WHERE LOWER(subject) = ? AND LOWER(relation) = ? AND LOWER(object) != ? AND scope = ?
            ORDER BY confidence DESC
            """,
            (fact.subject.lower(), fact.relation.lower(), fact.object.lower(), scope),
        ).fetchall()
        return [self._row_to_fact(row) for row in rows]

    def penalize(self, conn: sqlite3.Connection, fact_ids: list[str], amount: float = 0.15) -> None:
        for fid in fact_ids:
            conn.execute(
                "UPDATE facts SET confidence = MAX(confidence - ?, 0.1) WHERE id = ?",
                (amount, fid),
            )
        conn.commit()

    def recalibrate(self, conn: sqlite3.Connection) -> int:
        rows = conn.execute(
            "SELECT id, confidence, access_count FROM facts"
        ).fetchall()

        updated = 0
        for row in rows:
            access = row["access_count"] or 0
            base = row["confidence"]

            if access > 10:
                boost = min(access * 0.01, 0.2)
                new_conf = min(base + boost, 1.0)
            elif access == 0 and base > 0.6:
                new_conf = base - 0.02
            else:
                continue

            if abs(new_conf - base) > 0.001:
                conn.execute("UPDATE facts SET confidence = ? WHERE id = ?", (new_conf, row["id"]))
                updated += 1

        conn.commit()
        return updated

    def _row_to_fact(self, row) -> Fact:
        keys = row.keys()
        return Fact(
            id=row["id"],
            subject=row["subject"],
            relation=row["relation"],
            object=row["object"],
            confidence=row["confidence"],
            source_memory_id=row["source_memory_id"],
            scope=row["scope"],
            created_at=row["created_at"],
            temporal=row["temporal"] if "temporal" in keys else None,
            access_count=row["access_count"] if "access_count" in keys else 0,
        )
