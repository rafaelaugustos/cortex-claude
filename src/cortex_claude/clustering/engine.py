from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from cortex_claude.facts.normalizer import normalize_entity
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
    # How many incremental cluster_scope() runs happen before a reassignment
    # pass considers moving stale (poorly-fit) memories to a better cluster.
    # 0 disables reassignment entirely. See ClusteringEngine.reassign_stale.
    reassign_after_runs: int = 10
    # A member is "stale" if its similarity to its own cluster's centroid
    # has drifted below threshold * this factor — i.e. it's no longer a
    # confident fit for the cluster it's sitting in.
    reassign_drift_factor: float = 0.9

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
        cfg.reassign_after_runs = raw.get("reassign_after_runs", cfg.reassign_after_runs)
        cfg.reassign_drift_factor = raw.get("reassign_drift_factor", cfg.reassign_drift_factor)
        return cfg


@dataclass
class ClusterStats:
    assigned: int = 0
    new_clusters: int = 0
    relabeled: int = 0
    skipped: int = 0


@dataclass
class ReassignStats:
    moved: int = 0
    examined: int = 0
    emptied_clusters: int = 0


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return _cosine_with_norms(a, float(np.linalg.norm(a)), b, float(np.linalg.norm(b)))


def _cosine_with_norms(a: np.ndarray, na: float, b: np.ndarray, nb: float) -> float:
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

    Note: incremental assignment (cluster_scope) is append-only — a memory
    is only ever considered while its `cluster_id` is NULL, so a single run
    never migrates an already-assigned memory even if a better-fitting
    cluster appears later. Memories are processed in a fixed `created_at
    ASC` order so repeated runs over the same data are deterministic.
    `reassign_stale` mitigates drift from the append-only design with a
    separate, periodic pass that moves poorly-fit memories to a better
    cluster (see its docstring) — this is targeted, not a full
    re-clustering. To force a full re-clustering (e.g. after tuning
    `similarity_threshold`), use `cortex_clusters action="backfill"`, which
    resets all assignments in the scope before re-running.
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
        # (id, centroid, precomputed norm, member_count) — norm is cached so
        # comparing the same centroid against many memories in this round
        # doesn't recompute np.linalg.norm(centroid) every time.
        centroids: list[tuple[int, np.ndarray, float, int]] = [
            (c.id, c.centroid, float(np.linalg.norm(c.centroid)), c.member_count)
            for c in existing
            if c.centroid is not None
        ]

        assignments: list[tuple[str, int]] = []
        touched_clusters: set[int] = set()

        for memory_id, emb in unclustered:
            emb_norm = float(np.linalg.norm(emb))
            best_id, best_sim = None, -1.0
            for cid, centroid, centroid_norm, _ in centroids:
                sim = _cosine_with_norms(emb, emb_norm, centroid, centroid_norm)
                if sim > best_sim:
                    best_sim = sim
                    best_id = cid

            if best_id is not None and best_sim >= self.config.similarity_threshold:
                cluster_id = best_id
                idx = next(i for i, c in enumerate(centroids) if c[0] == cluster_id)
                cid, centroid, _, count = centroids[idx]
                new_count = count + 1
                new_centroid = (centroid * count + emb) / new_count
                centroids[idx] = (cid, new_centroid, float(np.linalg.norm(new_centroid)), new_count)
                stats.assigned += 1
            else:
                cluster_id = self._clusters.create(conn, scope=scope, centroid=emb)
                centroids.append((cluster_id, emb.copy(), emb_norm, 1))
                stats.new_clusters += 1

            assignments.append((memory_id, cluster_id))
            touched_clusters.add(cluster_id)

        self._memories.set_cluster_batch(conn, assignments)

        for cid, centroid, _, count in centroids:
            if cid in touched_clusters:
                self._clusters.update_centroid(conn, cid, centroid, member_count=count)

        for cid in touched_clusters:
            if self._relabel_cluster(conn, cid):
                stats.relabeled += 1

        return stats

    def reassign_stale(self, conn: sqlite3.Connection, scope: str) -> ReassignStats:
        """Move poorly-fit memories to a better cluster.

        Clustering is normally append-only (see class docstring) — this is
        the mitigation for that: a periodic, targeted pass (not a full
        re-clustering) that only touches memories whose similarity to their
        *own* cluster's centroid has drifted below
        `threshold * reassign_drift_factor`. For each such memory, it finds
        the best-fitting cluster among all existing centroids in the scope
        and moves the memory there if that's a different, better-fitting
        cluster. Both the origin and destination clusters' centroids and
        member_counts are updated. A cluster left with zero members is
        deleted.
        """
        stats = ReassignStats()
        if not self.config.enabled or self.config.reassign_after_runs <= 0:
            return stats

        existing = self._clusters.list_for_scope(conn, scope)
        centroids: dict[int, tuple[np.ndarray, float, int]] = {
            c.id: (c.centroid, float(np.linalg.norm(c.centroid)), c.member_count)
            for c in existing
            if c.centroid is not None
        }
        if len(centroids) < 2:
            return stats

        members = self._memories.iter_clustered_with_embeddings(conn, scope)
        threshold = self.config.similarity_threshold * self.config.reassign_drift_factor

        moves: list[tuple[str, int, int]] = []  # (memory_id, from_cluster, to_cluster)
        for memory_id, emb, current_cluster_id in members:
            current = centroids.get(current_cluster_id)
            if current is None:
                continue
            emb_norm = float(np.linalg.norm(emb))
            current_sim = _cosine_with_norms(emb, emb_norm, current[0], current[1])
            if current_sim >= threshold:
                continue

            stats.examined += 1
            best_id, best_sim = current_cluster_id, current_sim
            for cid, (centroid, centroid_norm, _) in centroids.items():
                sim = _cosine_with_norms(emb, emb_norm, centroid, centroid_norm)
                if sim > best_sim:
                    best_sim = sim
                    best_id = cid

            if best_id != current_cluster_id:
                moves.append((memory_id, current_cluster_id, best_id))

        if not moves:
            return stats

        # Apply moves against the DB (member_count/centroid recomputed from
        # ground truth afterward, not tracked incrementally — reassignment
        # is infrequent enough that re-reading is cheap and avoids drift
        # between in-memory bookkeeping and what's actually stored).
        self._memories.set_cluster_batch(
            conn, [(mid, to_cid) for mid, _, to_cid in moves]
        )
        stats.moved = len(moves)

        touched: set[int] = set()
        for _, from_cid, to_cid in moves:
            touched.add(from_cid)
            touched.add(to_cid)

        for cid in touched:
            remaining = self._memories.get_embeddings_for_cluster(conn, cid)
            if not remaining:
                self._clusters.delete(conn, cid)
                stats.emptied_clusters += 1
                continue
            new_centroid = np.mean(remaining, axis=0)
            self._clusters.update_centroid(conn, cid, new_centroid, member_count=len(remaining))
            self._relabel_cluster(conn, cid)

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
                t = normalize_entity(token)
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
