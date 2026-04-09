from __future__ import annotations

import numpy as np

from cortex_claude.models.memory import Memory
from cortex_claude.storage.database import StorageManager
from cortex_claude.storage.memory_repo import MemoryRepository


def test_save_and_get(storage_manager: StorageManager):
    repo = MemoryRepository()
    conn = storage_manager.get_database("global")

    memory = Memory(content="The API uses JWT for authentication", scope="global")
    embedding = np.random.randn(384).astype(np.float32)
    embedding = embedding / np.linalg.norm(embedding)

    repo.save(conn, memory, embedding)

    retrieved = repo.get(conn, memory.id)
    assert retrieved is not None
    assert retrieved.content == memory.content
    assert retrieved.scope == "global"


def test_vector_search(storage_manager: StorageManager):
    repo = MemoryRepository()
    conn = storage_manager.get_database("global")

    base = np.random.randn(384).astype(np.float32)
    base = base / np.linalg.norm(base)

    similar = base + np.random.randn(384).astype(np.float32) * 0.1
    similar = similar / np.linalg.norm(similar)

    different = np.random.randn(384).astype(np.float32)
    different = different / np.linalg.norm(different)

    m1 = Memory(content="Similar memory", scope="global")
    m2 = Memory(content="Different memory", scope="global")

    repo.save(conn, m1, similar)
    repo.save(conn, m2, different)

    results = repo.search_by_vector(conn, base, limit=2)
    assert len(results) == 2
    assert results[0][0] == m1.id
    assert results[0][1] > results[1][1]


def test_delete(storage_manager: StorageManager):
    repo = MemoryRepository()
    conn = storage_manager.get_database("global")

    memory = Memory(content="Temporary memory", scope="global")
    embedding = np.random.randn(384).astype(np.float32)

    repo.save(conn, memory, embedding)
    assert repo.get(conn, memory.id) is not None

    repo.delete(conn, memory.id)
    assert repo.get(conn, memory.id) is None


def test_count(storage_manager: StorageManager):
    repo = MemoryRepository()
    conn = storage_manager.get_database("global")

    assert repo.count(conn) == 0

    for i in range(3):
        m = Memory(content=f"Memory {i}", scope="global")
        e = np.random.randn(384).astype(np.float32)
        repo.save(conn, m, e)

    assert repo.count(conn) == 3


def test_list_scopes(storage_manager: StorageManager):
    storage_manager.get_database("global")
    storage_manager.get_database("project:api")

    scopes = storage_manager.list_scopes()
    assert "global" in scopes
    assert "project:api" in scopes
