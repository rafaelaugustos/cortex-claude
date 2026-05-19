from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from cortex_claude.storage import ClusterRepository, MemoryRepository
from cortex_claude.storage.fact_repo import FactRepository


@dataclass
class ClusteringConfig:
    enabled: bool = True
    similarity_threshold: float = 0.70
    min_members_for_label: int = 2
    label_top_n_entities: int = 3
    max_label_length: int = 60
    saves_between_runs: int = 20
    cooldown_seconds: int = 300

    @classmethod
    def from_dict(cls, raw: dict) -> ClusteringConfig:
        cfg = cls()
        if not raw:
            return cfg
        cfg.enabled = raw.get("enabled", cfg.enabled)
        cfg.similarity_threshold = raw.get("similarity_threshold", cfg.similarity_threshold)
        cfg.min_members_for_label = raw.get("min_members_for_label", cfg.min_members_for_label)
        cfg.label_top_n_entities = raw.get("label_top_n_entities", cfg.label_top_n_entities)
        cfg.max_label_length = raw.get("max_label_length", cfg.max_label_length)
        cfg.saves_between_runs = raw.get("saves_between_runs", cfg.saves_between_runs)
        cfg.cooldown_seconds = raw.get("cooldown_seconds", cfg.cooldown_seconds)
        return cfg


@dataclass
class ClusterStats:
    assigned: int = 0
    new_clusters: int = 0
    relabeled: int = 0
    skipped: int = 0


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class ClusteringEngine:
    """Incremental clustering by cosine similarity to existing centroids.

    For each unclustered memory:
      - Compute similarity to every cluster centroid in the scope.
      - If max similarity >= threshold: assign to that cluster, update centroid (running mean).
      - Else: create new cluster seeded by this memory's embedding.

    Labels are derived from the most frequent subjects/objects in the cluster's facts.
    """

    def __init__(
        self,
        config: ClusteringConfig | None = None,
        memory_repo: MemoryRepository | None = None,
        cluster_repo: ClusterRepository | None = None,
        fact_repo: FactRepository | None = None,
    ) -> None:
        self.config = config or ClusteringConfig()
        self._memories = memory_repo or MemoryRepository()
        self._clusters = cluster_repo or ClusterRepository()
        self._facts = fact_repo or FactRepository()

    def cluster_scope(self, conn: sqlite3.Connection, scope: str) -> ClusterStats:
        stats = ClusterStats()
        if not self.config.enabled:
            stats.skipped = 1
            return stats

        unclustered = self._memories.iter_with_embeddings(conn, unclustered_only=True)
        if not unclustered:
            return stats

        existing = self._clusters.list_for_scope(conn, scope)
        centroids: list[tuple[int, np.ndarray, int]] = [
            (c.id, c.centroid, c.member_count) for c in existing if c.centroid is not None
        ]

        assignments: list[tuple[str, int]] = []
        touched_clusters: set[int] = set()

        for memory_id, emb in unclustered:
            best_id, best_sim = None, -1.0
            for cid, centroid, _ in centroids:
                sim = _cosine(emb, centroid)
                if sim > best_sim:
                    best_sim = sim
                    best_id = cid

            if best_id is not None and best_sim >= self.config.similarity_threshold:
                cluster_id = best_id
                idx = next(i for i, c in enumerate(centroids) if c[0] == cluster_id)
                cid, centroid, count = centroids[idx]
                new_count = count + 1
                new_centroid = (centroid * count + emb) / new_count
                centroids[idx] = (cid, new_centroid, new_count)
                stats.assigned += 1
            else:
                cluster_id = self._clusters.create(conn, scope=scope, centroid=emb)
                centroids.append((cluster_id, emb.copy(), 1))
                stats.new_clusters += 1

            assignments.append((memory_id, cluster_id))
            touched_clusters.add(cluster_id)

        self._memories.set_cluster_batch(conn, assignments)

        for cid, centroid, count in centroids:
            if cid in touched_clusters:
                self._clusters.update_centroid(conn, cid, centroid, member_count=count)

        for cid in touched_clusters:
            if self._relabel_cluster(conn, cid):
                stats.relabeled += 1

        return stats

    def _relabel_cluster(self, conn: sqlite3.Connection, cluster_id: int) -> bool:
        cluster = self._clusters.get(conn, cluster_id)
        if cluster is None or cluster.member_count < self.config.min_members_for_label:
            return False

        rows = conn.execute(
            """
            SELECT f.subject, f.object
            FROM facts f
            JOIN memories m ON m.id = f.source_memory_id
            WHERE m.cluster_id = ?
            """,
            (cluster_id,),
        ).fetchall()

        if not rows:
            return False

        counter: Counter[str] = Counter()
        for subject, obj in rows:
            for token in (subject, obj):
                if not token:
                    continue
                t = token.strip().lower()
                if len(t) < 3:
                    continue
                if " " in t and len(t.split()) > 3:
                    continue
                if len(t) > 30:
                    continue
                counter[t] += 1

        if not counter:
            return False

        top = [t for t, _ in counter.most_common(self.config.label_top_n_entities)]
        label = ", ".join(top)[: self.config.max_label_length]

        if label and label != (cluster.label or ""):
            self._clusters.set_label(conn, cluster_id, label)
            return True
        return False
