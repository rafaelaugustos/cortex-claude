from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

import numpy as np


@dataclass
class Cluster:
    id: int
    scope: str
    label: str | None
    centroid: np.ndarray | None
    member_count: int
    updated_at: int


class ClusterRepository:
    def create(
        self,
        conn: sqlite3.Connection,
        scope: str,
        centroid: np.ndarray,
        label: str | None = None,
    ) -> int:
        now = int(time.time() * 1000)
        cursor = conn.execute(
            """
            INSERT INTO clusters (scope, label, centroid, member_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (scope, label, centroid.astype(np.float32).tobytes(), 0, now),
        )
        conn.commit()
        return int(cursor.lastrowid)

    def update_centroid(
        self,
        conn: sqlite3.Connection,
        cluster_id: int,
        centroid: np.ndarray,
        member_count: int,
        label: str | None = None,
    ) -> None:
        now = int(time.time() * 1000)
        if label is not None:
            conn.execute(
                """
                UPDATE clusters
                SET centroid = ?, member_count = ?, label = ?, updated_at = ?
                WHERE id = ?
                """,
                (centroid.astype(np.float32).tobytes(), member_count, label, now, cluster_id),
            )
        else:
            conn.execute(
                """
                UPDATE clusters
                SET centroid = ?, member_count = ?, updated_at = ?
                WHERE id = ?
                """,
                (centroid.astype(np.float32).tobytes(), member_count, now, cluster_id),
            )
        conn.commit()

    def set_label(self, conn: sqlite3.Connection, cluster_id: int, label: str) -> None:
        conn.execute(
            "UPDATE clusters SET label = ?, updated_at = ? WHERE id = ?",
            (label, int(time.time() * 1000), cluster_id),
        )
        conn.commit()

    def list_for_scope(self, conn: sqlite3.Connection, scope: str) -> list[Cluster]:
        rows = conn.execute(
            """
            SELECT id, scope, label, centroid, member_count, updated_at
            FROM clusters
            WHERE scope = ?
            ORDER BY member_count DESC
            """,
            (scope,),
        ).fetchall()
        out: list[Cluster] = []
        for row in rows:
            centroid = np.frombuffer(row[3], dtype=np.float32) if row[3] else None
            out.append(
                Cluster(
                    id=row[0],
                    scope=row[1],
                    label=row[2],
                    centroid=centroid,
                    member_count=row[4],
                    updated_at=row[5],
                )
            )
        return out

    def get(self, conn: sqlite3.Connection, cluster_id: int) -> Cluster | None:
        row = conn.execute(
            "SELECT id, scope, label, centroid, member_count, updated_at FROM clusters WHERE id = ?",
            (cluster_id,),
        ).fetchone()
        if row is None:
            return None
        centroid = np.frombuffer(row[3], dtype=np.float32) if row[3] else None
        return Cluster(
            id=row[0],
            scope=row[1],
            label=row[2],
            centroid=centroid,
            member_count=row[4],
            updated_at=row[5],
        )

    def delete(self, conn: sqlite3.Connection, cluster_id: int) -> None:
        conn.execute("DELETE FROM clusters WHERE id = ?", (cluster_id,))
        conn.commit()

    def recount_members(self, conn: sqlite3.Connection, scope: str) -> None:
        """Recompute member_count for all clusters in scope based on memories.cluster_id."""
        conn.execute(
            """
            UPDATE clusters
            SET member_count = COALESCE(
                (SELECT COUNT(*) FROM memories WHERE memories.cluster_id = clusters.id),
                0
            )
            WHERE scope = ?
            """,
            (scope,),
        )
        conn.commit()
