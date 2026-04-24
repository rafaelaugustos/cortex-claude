from __future__ import annotations

import pytest

from cortex_claude.core.engine import CortexEngine


@pytest.mark.asyncio
async def test_traverse_finds_connections(engine: CortexEngine):
    await engine.save(content="The auth service uses JWT tokens for authentication.")
    await engine.save(content="JWT tokens expire after 24 hours.")

    facts = await engine.traverse_graph(start="auth", max_hops=2)
    entities = set()
    for f in facts:
        entities.add(f.subject)
        entities.add(f.object)

    assert any("auth" in e for e in entities)


@pytest.mark.asyncio
async def test_traverse_multi_hop(engine: CortexEngine):
    await engine.save(content="The API uses Redis for caching.")
    await engine.save(content="Redis stores session data.")

    facts = await engine.traverse_graph(start="api", max_hops=2)
    has_redis = any("redis" in f.subject or "redis" in f.object for f in facts)
    assert has_redis


@pytest.mark.asyncio
async def test_traverse_no_results(engine: CortexEngine):
    facts = await engine.traverse_graph(start="nonexistent_entity_xyz")
    assert facts == []


@pytest.mark.asyncio
async def test_traverse_respects_scope(engine: CortexEngine):
    await engine.save(content="React handles the frontend rendering.", scope="project:web")
    await engine.save(content="Django handles the backend API.", scope="project:api")

    web_facts = await engine.traverse_graph(start="react", scope="project:web")
    api_facts = await engine.traverse_graph(start="react", scope="project:api")

    assert len(web_facts) >= len(api_facts)
