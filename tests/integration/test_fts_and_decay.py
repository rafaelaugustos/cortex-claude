from __future__ import annotations

import pytest

from cortex_claude.core.engine import CortexEngine


@pytest.mark.asyncio
async def test_fts_finds_exact_match(engine: CortexEngine):
    await engine.save(content="The JWT_SECRET_KEY is stored in environment variables.")

    result = await engine.recall(query="JWT_SECRET_KEY", depth="full", max_tokens=500)
    has_match = any("JWT_SECRET_KEY" in m.content for m in result.memories)
    assert has_match


@pytest.mark.asyncio
async def test_decay_affects_ranking(engine: CortexEngine):
    r1 = await engine.save(content="Fresh information about the database schema.")
    r2 = await engine.save(content="Old information about the database config.")

    # Simulate accessing r1 multiple times to boost its decay score
    conn = engine._storage.get_database("global")
    for _ in range(5):
        engine._memory_repo.update_accessed(conn, r1.memory_id)

    await engine.run_decay()

    result = await engine.recall(query="database", depth="full", max_tokens=1000)
    assert len(result.memories) >= 2

    # The frequently accessed memory should rank higher
    if len(result.memories) >= 2:
        scores = {m.memory_id: m.score for m in result.memories}
        if r1.memory_id in scores and r2.memory_id in scores:
            assert scores[r1.memory_id] >= scores[r2.memory_id]


@pytest.mark.asyncio
async def test_decay_on_initialize(engine: CortexEngine):
    await engine.save(content="Memory before initialization.")

    engine.initialize()

    conn = engine._storage.get_database("global")
    memory = conn.execute("SELECT decay_score FROM memories LIMIT 1").fetchone()
    assert memory is not None
    assert memory[0] > 0


@pytest.mark.asyncio
async def test_recall_combines_fts_and_vector(engine: CortexEngine):
    await engine.save(content="Error code ERR_CONNECTION_REFUSED appears in production logs.")
    await engine.save(content="The application connects to the database on port 5432.")

    result = await engine.recall(query="ERR_CONNECTION_REFUSED", depth="full", max_tokens=500)
    assert len(result.memories) > 0
    has_error = any("ERR_CONNECTION_REFUSED" in m.content for m in result.memories)
    assert has_error
