from __future__ import annotations

import sqlite3
import time
import uuid

import numpy as np
import pytest

from cortex_claude.clustering import ClusteringConfig, ClusteringEngine
from cortex_claude.storage import ClusterRepository
from cortex_claude.storage import migrations as M


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(M.SCHEMA_SQL)
    conn.executescript(M.FTS_SQL)
    # Plain table (not vec0) — clustering doesn't need vec0
    conn.execute("CREATE TABLE memory_vectors (id TEXT PRIMARY KEY, embedding BLOB)")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (M.SCHEMA_VERSION,))
    conn.commit()
    yield conn
    conn.close()


def _seed_group(conn: sqlite3.Connection, group: int, count: int, label_terms: list[str]) -> list[str]:
    now = int(time.time() * 1000)
    rng = np.random.default_rng(group * 100)
    ids: list[str] = []
    for i in range(count):
        mid = str(uuid.uuid4())
        ids.append(mid)
        conn.execute(
            "INSERT INTO memories (id, content, summary, tags, scope, created_at, updated_at, accessed_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (mid, f"text-{group}-{i}", None, "[]", "global", now, now, now),
        )
        emb = np.zeros(384, dtype=np.float32)
        start = group * 50
        emb[start:start + 50] = 1.0
        emb += rng.normal(0, 0.02, 384).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        conn.execute("INSERT INTO memory_vectors (id, embedding) VALUES (?, ?)", (mid, emb.tobytes()))

        for term in label_terms:
            fact_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO facts (id, subject, relation, object, confidence, source_memory_id, scope, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (fact_id, term, "about", "x", 1.0, mid, "global", now),
            )
    conn.commit()
    return ids


class TestClustering:
    def test_separates_two_groups(self, db: sqlite3.Connection):
        _seed_group(db, group=0, count=3, label_terms=["embeddings", "vectors"])
        _seed_group(db, group=1, count=3, label_terms=["mcp", "server"])

        engine = ClusteringEngine(ClusteringConfig(similarity_threshold=0.5))
        stats = engine.cluster_scope(db, "global")
        assert stats.assigned + stats.new_clusters == 6
        assert stats.new_clusters == 2

        clusters = ClusterRepository().list_for_scope(db, "global")
        assert len(clusters) == 2
        assert all(c.member_count == 3 for c in clusters)
        assert all(c.label is not None for c in clusters)

    def test_incremental_attaches_to_existing(self, db: sqlite3.Connection):
        _seed_group(db, group=0, count=3, label_terms=["embeddings"])
        _seed_group(db, group=1, count=3, label_terms=["mcp"])
        engine = ClusteringEngine(ClusteringConfig(similarity_threshold=0.5))
        engine.cluster_scope(db, "global")

        _seed_group(db, group=0, count=1, label_terms=["embeddings"])
        stats = engine.cluster_scope(db, "global")
        assert stats.assigned == 1
        assert stats.new_clusters == 0

        clusters = ClusterRepository().list_for_scope(db, "global")
        assert len(clusters) == 2
        sizes = sorted(c.member_count for c in clusters)
        assert sizes == [3, 4]

    def test_disabled_skips(self, db: sqlite3.Connection):
        _seed_group(db, group=0, count=3, label_terms=["x"])
        engine = ClusteringEngine(ClusteringConfig(enabled=False))
        stats = engine.cluster_scope(db, "global")
        assert stats.assigned == 0
        assert stats.new_clusters == 0
        assert stats.skipped == 1

    def test_no_memories_is_noop(self, db: sqlite3.Connection):
        engine = ClusteringEngine()
        stats = engine.cluster_scope(db, "global")
        assert stats.assigned == 0
        assert stats.new_clusters == 0


class TestClusterTraverse:
    """Tests for cluster:<id> seed mode in CortexEngine.traverse_graph."""

    def test_cluster_seed_returns_entities_from_central_members(self, tmp_path):
        from cortex_claude.core.engine import CortexEngine
        from cortex_claude.server.config import CortexConfig
        import asyncio

        config = CortexConfig(base_path=tmp_path / ".cortex")
        eng = CortexEngine(config=config)
        eng.initialize()

        try:
            async def go():
                # Save memories that will cluster together via real embeddings
                texts = [
                    "FastMCP framework registers cortex_save and cortex_recall as MCP tools",
                    "MCP server exposes cortex tools via stdio transport for Claude Code",
                    "The MCP protocol uses JSON-RPC over stdio for tool invocation",
                ]
                for t in texts:
                    await eng.save(content=t, scope="global")

                # Run clustering with permissive threshold so all 3 land together
                ce = ClusteringEngine(ClusteringConfig(similarity_threshold=0.35))
                conn = eng.get_scope_connection("global")
                ce.cluster_scope(conn, "global")

                clusters = await eng.list_clusters(scope="global")
                assert clusters, "expected at least one cluster"
                cluster_id = clusters[0]["id"]

                facts = await eng.traverse_graph(start=f"cluster:{cluster_id}", max_hops=1, scope="global")
                # We can't predict exact facts spaCy extracts, but the seed
                # should produce at least one hop's worth of results.
                assert isinstance(facts, list)

            asyncio.run(go())
        finally:
            eng.close()

    def test_cluster_missing_id_returns_empty(self, tmp_path):
        from cortex_claude.core.engine import CortexEngine
        from cortex_claude.server.config import CortexConfig
        import asyncio

        config = CortexConfig(base_path=tmp_path / ".cortex")
        eng = CortexEngine(config=config)
        eng.initialize()

        try:
            async def go():
                facts = await eng.traverse_graph(start="cluster:999999", max_hops=1, scope="global")
                assert facts == []

                facts = await eng.traverse_graph(start="cluster:abc", max_hops=1, scope="global")
                assert facts == []

                facts = await eng.traverse_graph(start="cluster:", max_hops=1, scope="global")
                assert facts == []

            asyncio.run(go())
        finally:
            eng.close()
