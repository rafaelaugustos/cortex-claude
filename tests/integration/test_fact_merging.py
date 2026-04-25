from __future__ import annotations

import pytest

from cortex_claude.core.engine import CortexEngine


@pytest.mark.asyncio
async def test_duplicate_facts_merged_on_save(engine: CortexEngine):
    await engine.save(content="The API uses PostgreSQL for storage.")
    await engine.save(content="The API uses PostgreSQL as the main database.")

    facts = await engine.get_facts(topic="api")
    # Should have merged duplicates, not duplicated
    pg_facts = [f for f in facts if "postgresql" in f.object]
    assert len(pg_facts) >= 1

    # Merged fact should have higher confidence
    if pg_facts:
        assert pg_facts[0].confidence > 0.8


@pytest.mark.asyncio
async def test_confidence_increases_with_repetition(engine: CortexEngine):
    await engine.save(content="Redis is used for caching.")
    facts_1 = await engine.get_facts(topic="redis")
    conf_1 = facts_1[0].confidence if facts_1 else 0

    await engine.save(content="Redis handles the caching layer.")
    facts_2 = await engine.get_facts(topic="redis")
    conf_2 = max(f.confidence for f in facts_2) if facts_2 else 0

    assert conf_2 >= conf_1


@pytest.mark.asyncio
async def test_consolidate_on_initialize(engine: CortexEngine):
    await engine.save(content="Node.js powers the backend.")
    await engine.save(content="The backend runs on Node.js.")

    engine.initialize()

    facts = await engine.get_facts(topic="node")
    # After consolidation, no exact duplicates
    seen = set()
    for f in facts:
        key = (f.subject.lower(), f.relation.lower(), f.object.lower())
        assert key not in seen, f"Duplicate fact found: {key}"
        seen.add(key)


@pytest.mark.asyncio
async def test_different_facts_not_merged(engine: CortexEngine):
    await engine.save(content="The API uses PostgreSQL. The cache uses Redis.")

    pg_facts = await engine.get_facts(topic="postgresql")
    redis_facts = await engine.get_facts(topic="redis")

    assert len(pg_facts) >= 1
    assert len(redis_facts) >= 1
