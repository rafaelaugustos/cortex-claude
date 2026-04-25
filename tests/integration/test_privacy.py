from __future__ import annotations

import pytest

from cortex_claude.core.engine import CortexEngine


@pytest.mark.asyncio
async def test_save_strips_private_content(engine: CortexEngine):
    await engine.save(
        content="The API uses JWT. <private>API_KEY=sk-abc123</private> Auth works well."
    )

    result = await engine.recall(query="API JWT auth", depth="full", max_tokens=500)
    for m in result.memories:
        assert "sk-abc123" not in m.content
        assert "API_KEY" not in m.content


@pytest.mark.asyncio
async def test_save_fully_private_is_skipped(engine: CortexEngine):
    result = await engine.save(content="<private>Everything is secret</private>")
    assert result.memory_id == ""
    assert result.tokens_stored == 0


@pytest.mark.asyncio
async def test_save_preserves_public_content(engine: CortexEngine):
    await engine.save(
        content="Database is PostgreSQL. <private>password=hunter2</private> Uses port 5432."
    )

    result = await engine.recall(query="database", depth="full", max_tokens=500)
    assert len(result.memories) > 0
    has_postgres = any("PostgreSQL" in m.content for m in result.memories)
    assert has_postgres


@pytest.mark.asyncio
async def test_facts_dont_contain_private(engine: CortexEngine):
    await engine.save(
        content="The service uses Redis. <private>REDIS_URL=redis://secret:6379</private>"
    )

    facts = await engine.get_facts(topic="redis")
    for f in facts:
        assert "secret" not in f.subject
        assert "secret" not in f.object
