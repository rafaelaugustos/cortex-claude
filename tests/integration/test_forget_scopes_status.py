from __future__ import annotations

import pytest

from cortex_claude.core.engine import CortexEngine


@pytest.mark.asyncio
async def test_forget_dry_run(engine: CortexEngine):
    await engine.save(content="Temporary data to forget")

    result = await engine.forget(query="temporary data", dry_run=True)
    assert len(result.deleted) > 0
    assert result.dry_run is True

    recall = await engine.recall(query="temporary data", depth="full", max_tokens=500)
    assert len(recall.memories) > 0


@pytest.mark.asyncio
async def test_forget_actual_delete(engine: CortexEngine):
    save_result = await engine.save(content="Delete me permanently")

    result = await engine.forget(memory_id=save_result.memory_id, dry_run=False)
    assert len(result.deleted) == 1
    assert result.dry_run is False

    recall = await engine.recall(query="delete me permanently", depth="full", max_tokens=500)
    has_deleted = any("Delete me permanently" in m.content for m in recall.memories)
    assert not has_deleted


@pytest.mark.asyncio
async def test_forget_no_match(engine: CortexEngine):
    result = await engine.forget(query="nonexistent thing xyz123")
    assert len(result.deleted) == 0


@pytest.mark.asyncio
async def test_forget_reports_deletions_grouped_by_actual_scope(engine: CortexEngine, tmp_path):
    """Regression: previously `target_scope` was overwritten on every match
    in the scope-search loop, so the report reflected only the
    last-iterated scope instead of where memories actually were deleted
    from. Configure two directories mapped to two different scopes so a
    single forget() call (scope=None) resolves and searches both, then
    verify the report attributes each deletion to its real scope."""
    dir_a = tmp_path / "repo_a"
    dir_b = tmp_path / "repo_b"
    dir_a.mkdir()
    dir_b.mkdir()

    await engine.manage_scopes(action="link", name="project:a", path=str(dir_a))
    await engine.manage_scopes(action="link", name="project:b", path=str(dir_b))

    a = await engine.save(content="Alpha project secret sauce", scope="project:a")
    b = await engine.save(content="Beta project secret recipe", scope="project:b")

    # cwd=dir_a resolves to ["project:a", "global"] only — forget with an
    # explicit memory_id still must search across whichever scopes resolve,
    # and correctly report which scope the deleted memory came from.
    result = await engine.forget(memory_id=a.memory_id, scope=None, cwd=str(dir_a), dry_run=False)
    assert result.deleted == [a.memory_id]
    assert result.deleted_by_scope == {"project:a": [a.memory_id]}

    result_b = await engine.forget(memory_id=b.memory_id, scope=None, cwd=str(dir_b), dry_run=False)
    assert result_b.deleted_by_scope == {"project:b": [b.memory_id]}


@pytest.mark.asyncio
async def test_forget_updates_cluster_member_count(engine: CortexEngine):
    from cortex_claude.clustering import ClusteringConfig, ClusteringEngine

    # Distinct-enough contents to avoid triggering save-time dedup merging,
    # which would collapse these into fewer memories than expected.
    texts = [
        "The billing service charges customers monthly via Stripe",
        "The billing service reconciles invoices with the accounting ledger",
        "The billing service sends dunning emails for failed payments",
    ]
    ids = []
    for text in texts:
        r = await engine.save(content=text, scope="global")
        ids.append(r.memory_id)

    conn = engine.get_scope_connection("global")
    ClusteringEngine(ClusteringConfig(similarity_threshold=0.3)).cluster_scope(conn, "global")

    clusters_before = await engine.list_clusters(scope="global")
    assert clusters_before, "expected at least one cluster to have formed"
    total_before = sum(c["member_count"] for c in clusters_before)

    await engine.forget(memory_id=ids[0], dry_run=False)

    clusters_after = await engine.list_clusters(scope="global")
    total_after = sum(c["member_count"] for c in clusters_after)
    assert total_after == total_before - 1


@pytest.mark.asyncio
async def test_forget_recomputes_cluster_centroid(engine: CortexEngine):
    from cortex_claude.clustering import ClusteringConfig, ClusteringEngine
    from cortex_claude.storage import ClusterRepository, MemoryRepository
    import numpy as np

    texts = [
        "The billing service charges customers monthly via Stripe",
        "The billing service reconciles invoices with the accounting ledger",
        "The billing service sends dunning emails for failed payments",
    ]
    ids = []
    for text in texts:
        r = await engine.save(content=text, scope="global")
        ids.append(r.memory_id)

    conn = engine.get_scope_connection("global")
    ClusteringEngine(ClusteringConfig(similarity_threshold=0.3)).cluster_scope(conn, "global")

    memory_repo = MemoryRepository()
    cluster_repo = ClusterRepository()
    cluster_id = memory_repo.get_cluster_id(conn, ids[0])
    assert cluster_id is not None, "expected the first memory to land in a cluster"

    await engine.forget(memory_id=ids[0], dry_run=False)

    remaining = memory_repo.get_embeddings_for_cluster(conn, cluster_id)
    if remaining:
        expected_centroid = np.mean(remaining, axis=0)
        cluster = cluster_repo.get(conn, cluster_id)
        assert cluster is not None
        np.testing.assert_allclose(cluster.centroid, expected_centroid, rtol=1e-5)
    else:
        # All members of that cluster were deleted — the cluster itself
        # should be gone rather than lingering with a stale centroid.
        assert cluster_repo.get(conn, cluster_id) is None


@pytest.mark.asyncio
async def test_forget_deletes_cluster_left_with_zero_members(engine: CortexEngine):
    from cortex_claude.clustering import ClusteringConfig, ClusteringEngine
    from cortex_claude.storage import ClusterRepository, MemoryRepository

    r = await engine.save(content="A singular, uniquely-worded memory about zephyrs", scope="global")

    conn = engine.get_scope_connection("global")
    ClusteringEngine(ClusteringConfig(similarity_threshold=0.99)).cluster_scope(conn, "global")

    memory_repo = MemoryRepository()
    cluster_repo = ClusterRepository()
    cluster_id = memory_repo.get_cluster_id(conn, r.memory_id)
    assert cluster_id is not None

    await engine.forget(memory_id=r.memory_id, dry_run=False)

    assert cluster_repo.get(conn, cluster_id) is None


@pytest.mark.asyncio
async def test_scopes_list(engine: CortexEngine):
    await engine.save(content="Global memory", scope="global")
    await engine.save(content="Project memory", scope="project:test")

    result = await engine.manage_scopes(action="list")
    assert result["action"] == "list"
    names = [s["name"] for s in result["scopes"]]
    assert "global" in names
    assert "project:test" in names


@pytest.mark.asyncio
async def test_scopes_create_and_delete(engine: CortexEngine):
    result = await engine.manage_scopes(action="create", name="custom:temp")
    assert result["status"] == "created"

    result = await engine.manage_scopes(action="delete", name="custom:temp")
    assert result["status"] == "deleted"


@pytest.mark.asyncio
async def test_scopes_cannot_delete_global(engine: CortexEngine):
    result = await engine.manage_scopes(action="delete", name="global")
    assert "cannot" in result["status"]


@pytest.mark.asyncio
async def test_scopes_info(engine: CortexEngine):
    await engine.save(content="Some info for status", scope="global")

    result = await engine.manage_scopes(action="info", name="global")
    assert result["memories"] >= 1


@pytest.mark.asyncio
async def test_status(engine: CortexEngine):
    await engine.save(content="Memory for status test")

    result = await engine.status()
    assert result.total_memories >= 1
    assert result.total_size_bytes > 0
    assert len(result.scopes) >= 1


@pytest.mark.asyncio
async def test_decay_run(engine: CortexEngine):
    await engine.save(content="Memory for decay test")

    updated = await engine.run_decay()
    assert updated >= 1
