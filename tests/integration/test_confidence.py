from __future__ import annotations

import pytest

from cortex_claude.core.engine import CortexEngine


@pytest.mark.asyncio
async def test_facts_gain_confidence_on_access(engine: CortexEngine):
    await engine.save(content="The API uses PostgreSQL for storage.")

    facts_1 = await engine.get_facts(topic="postgresql")
    conf_1 = facts_1[0].confidence if facts_1 else 0

    # Access again — should boost
    facts_2 = await engine.get_facts(topic="postgresql")
    conf_2 = facts_2[0].confidence if facts_2 else 0

    assert conf_2 > conf_1


@pytest.mark.asyncio
async def test_contradiction_lowers_old_fact(engine: CortexEngine):
    await engine.save(content="The database is MySQL.")

    facts_before = await engine.get_facts(topic="database")
    mysql_facts = [f for f in facts_before if "mysql" in f.object]
    conf_before = mysql_facts[0].confidence if mysql_facts else 0

    # Contradict: same subject + exclusive relation "be", different object
    await engine.save(content="The database is PostgreSQL.")

    facts_after = await engine.get_facts(topic="mysql")
    mysql_after = [f for f in facts_after if "mysql" in f.object]
    conf_after = mysql_after[0].confidence if mysql_after else 0

    # MySQL fact should have lower confidence now
    assert conf_after < conf_before


@pytest.mark.asyncio
async def test_recalibrate_on_initialize(engine: CortexEngine):
    await engine.save(content="Redis handles caching.")

    # Access many times to build up access_count
    for _ in range(12):
        await engine.get_facts(topic="redis")

    engine.initialize()

    facts = await engine.get_facts(topic="redis")
    if facts:
        # Highly accessed fact should have high confidence
        assert facts[0].confidence > 0.8


@pytest.mark.asyncio
async def test_non_contradicting_facts_unaffected(engine: CortexEngine):
    await engine.save(content="The API uses JWT for auth.")

    facts_before = await engine.get_facts(topic="jwt")
    conf_before = facts_before[0].confidence if facts_before else 0

    # Save something about a different relation — not a contradiction
    await engine.save(content="The API uses rate limiting at 1000 req/min.")

    facts_after = await engine.get_facts(topic="jwt")
    conf_after = facts_after[0].confidence if facts_after else 0

    # JWT fact should not have been penalized
    assert conf_after >= conf_before
