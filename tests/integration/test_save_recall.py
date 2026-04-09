from __future__ import annotations

import pytest

from cortex_claude.core.engine import CortexEngine


@pytest.mark.asyncio
async def test_save_and_recall(engine: CortexEngine):
    await engine.save(
        content="The authentication service uses JWT tokens with 24h expiry",
        tags=["auth", "jwt"],
    )

    result = await engine.recall(query="How does auth work?", max_tokens=500)

    assert len(result.memories) == 1
    assert "JWT" in result.memories[0].content
    assert result.total_tokens > 0


@pytest.mark.asyncio
async def test_recall_respects_token_budget(engine: CortexEngine):
    for i in range(5):
        await engine.save(content=f"Memory number {i} with some additional context to use tokens")

    result = await engine.recall(query="memory", max_tokens=30)
    assert result.total_tokens <= 30


@pytest.mark.asyncio
async def test_recall_empty_store(engine: CortexEngine):
    result = await engine.recall(query="anything")
    assert len(result.memories) == 0
    assert result.total_tokens == 0


@pytest.mark.asyncio
async def test_save_with_scope(engine: CortexEngine):
    await engine.save(content="Project-specific info", scope="project:web")

    result = await engine.recall(query="project info", scope="project:web")
    assert len(result.memories) == 1

    result_global = await engine.recall(query="project info", scope="global")
    assert len(result_global.memories) == 0


@pytest.mark.asyncio
async def test_recall_ranks_by_relevance(engine: CortexEngine):
    await engine.save(content="Python is a programming language used for data science")
    await engine.save(content="The database schema uses PostgreSQL with JSONB columns")
    await engine.save(content="React components handle the frontend UI rendering")

    result = await engine.recall(query="database schema", max_tokens=1000)
    assert len(result.memories) > 0
    assert "PostgreSQL" in result.memories[0].content
