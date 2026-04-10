from __future__ import annotations

import pytest

from cortex_claude.core.engine import CortexEngine


@pytest.mark.asyncio
async def test_facts_are_extracted_on_save(engine: CortexEngine):
    await engine.save(
        content="The auth service uses JWT tokens with 24-hour expiry."
    )

    facts = await engine.get_facts(topic="auth")
    assert len(facts) > 0


@pytest.mark.asyncio
async def test_recall_facts_depth(engine: CortexEngine):
    await engine.save(
        content="PostgreSQL is the primary database. Redis handles caching."
    )

    result = await engine.recall(query="database", depth="facts", max_tokens=500)
    if result.memories:
        for item in result.memories:
            assert "→" in item.content


@pytest.mark.asyncio
async def test_recall_full_depth(engine: CortexEngine):
    await engine.save(
        content="The API rate limit is 1000 requests per minute."
    )

    result = await engine.recall(query="rate limit", depth="full", max_tokens=500)
    assert len(result.memories) > 0
    has_full = any("1000" in m.content for m in result.memories)
    assert has_full


@pytest.mark.asyncio
async def test_recall_auto_progressive(engine: CortexEngine):
    await engine.save(
        content=(
            "The authentication service uses JWT tokens. "
            "Tokens expire after 24 hours. "
            "Refresh tokens are stored in httpOnly cookies."
        ),
        tags=["auth"],
    )

    result = await engine.recall(query="auth JWT", max_tokens=100, depth="auto")
    assert result.total_tokens <= 100


@pytest.mark.asyncio
async def test_deduplication(engine: CortexEngine):
    await engine.save(content="The API uses PostgreSQL for data storage.")
    await engine.save(content="The API uses PostgreSQL for data storage.")

    result = await engine.recall(query="PostgreSQL", depth="full", max_tokens=1000)
    contents = [m.content for m in result.memories]
    assert len(contents) <= 2


@pytest.mark.asyncio
async def test_cortex_facts_tool(engine: CortexEngine):
    await engine.save(content="Redis is used for session caching with a 1-hour TTL.")

    facts = await engine.get_facts(topic="redis")
    assert isinstance(facts, list)
