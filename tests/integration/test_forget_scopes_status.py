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
