import numpy as np
import pytest


@pytest.fixture
def local_engine(engine, monkeypatch):
    def embed(content):
        vector = np.zeros(384, dtype=np.float32)
        vector[0 if "MySQL" in content else 1] = 1
        return vector
    monkeypatch.setattr(engine._embeddings, "embed", embed)
    return engine


@pytest.mark.asyncio
async def test_edit_rebuilds_facts_summary_vector_and_fts(local_engine):
    engine = local_engine
    saved = await engine.save("The database is MySQL.")
    conn = engine.get_scope_connection("global")
    conn.execute("UPDATE memories SET summary='Old MySQL summary' WHERE id=?", (saved.memory_id,))
    conn.commit()
    assert engine.update_memory(saved.memory_id, "The database is PostgreSQL. <private>secret</private>", "global")
    memory = engine._memory_repo.get(conn, saved.memory_id)
    assert "secret" not in memory.content
    assert memory.summary is None
    facts = engine._fact_repo.search_by_memory(conn, saved.memory_id)
    assert any("postgresql" in fact.object for fact in facts)
    assert all("mysql" not in fact.object for fact in facts)
    embedding = conn.execute("SELECT embedding FROM memory_vectors WHERE id=?", (saved.memory_id,)).fetchone()[0]
    assert np.frombuffer(embedding, dtype=np.float32)[1] == 1
    assert engine._memory_repo.search_fts(conn, "PostgreSQL") == [saved.memory_id]
    assert not engine._memory_repo.search_fts(conn, "MySQL")


@pytest.mark.asyncio
async def test_failed_edit_rolls_back_every_representation(local_engine, monkeypatch):
    engine = local_engine
    saved = await engine.save("The database is MySQL.")
    def fail(*args, **kwargs):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(engine._fact_repo, "save_batch", fail)
    with pytest.raises(RuntimeError, match="simulated failure"):
        engine.update_memory(saved.memory_id, "The database is PostgreSQL.", "global")
    conn = engine.get_scope_connection("global")
    assert engine._memory_repo.get(conn, saved.memory_id).content == "The database is MySQL."
    embedding = conn.execute("SELECT embedding FROM memory_vectors WHERE id=?", (saved.memory_id,)).fetchone()[0]
    assert np.frombuffer(embedding, dtype=np.float32)[0] == 1
    assert engine._memory_repo.search_fts(conn, "MySQL") == [saved.memory_id]


@pytest.mark.asyncio
async def test_private_only_edit_does_not_erase_memory(local_engine):
    saved = await local_engine.save("The database is MySQL.")
    with pytest.raises(ValueError, match="entirely private"):
        local_engine.update_memory(saved.memory_id, "<private>hidden", "global")
    conn = local_engine.get_scope_connection("global")
    assert local_engine._memory_repo.get(conn, saved.memory_id).content == "The database is MySQL."
