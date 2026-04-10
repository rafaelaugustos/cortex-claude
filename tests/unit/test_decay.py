import time

import numpy as np

from cortex_claude.core.decay import recalculate_decay_scores
from cortex_claude.models.memory import Memory
from cortex_claude.storage.database import StorageManager
from cortex_claude.storage.memory_repo import MemoryRepository


def test_decay_recent_memory_high_score(storage_manager: StorageManager):
    repo = MemoryRepository()
    conn = storage_manager.get_database("global")

    memory = Memory(content="Recent memory", scope="global")
    embedding = np.random.randn(384).astype(np.float32)
    repo.save(conn, memory, embedding)

    updated = recalculate_decay_scores(conn)
    assert updated == 1

    refreshed = repo.get(conn, memory.id)
    assert refreshed.decay_score > 0.9


def test_decay_accessed_memory_gets_boost(storage_manager: StorageManager):
    repo = MemoryRepository()
    conn = storage_manager.get_database("global")

    m1 = Memory(content="Never accessed", scope="global")
    m2 = Memory(content="Accessed often", scope="global")

    e1 = np.random.randn(384).astype(np.float32)
    e2 = np.random.randn(384).astype(np.float32)

    repo.save(conn, m1, e1)
    repo.save(conn, m2, e2)

    for _ in range(5):
        repo.update_accessed(conn, m2.id)

    recalculate_decay_scores(conn)

    r1 = repo.get(conn, m1.id)
    r2 = repo.get(conn, m2.id)
    assert r2.decay_score > r1.decay_score
