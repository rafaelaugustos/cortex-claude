from __future__ import annotations

import json
from pathlib import Path

from cortex_claude.core.scope_manager import ScopeManager
from cortex_claude.core.token_budget import TokenBudget
from cortex_claude.embeddings import EmbeddingEngine, count_tokens
from cortex_claude.models.memory import Memory, RecallItem, RecallResult, SaveResult
from cortex_claude.storage import MemoryRepository, StorageManager


class CortexEngine:
    def __init__(self, base_path: Path | None = None):
        self._base_path = base_path or Path.home() / ".cortex-claude"
        self._storage = StorageManager(self._base_path)
        self._embeddings = EmbeddingEngine()
        self._scope_manager = ScopeManager(self._base_path)
        self._repo = MemoryRepository()

    async def save(
        self,
        content: str,
        tags: list[str] | None = None,
        scope: str | None = None,
        cwd: str = ".",
    ) -> SaveResult:
        write_scope = scope or self._scope_manager.get_write_scope(cwd)
        embedding = self._embeddings.embed(content)
        tokens = count_tokens(content)

        memory = Memory(
            content=content,
            tags=tags or [],
            scope=write_scope,
        )

        conn = self._storage.get_database(write_scope)
        self._repo.save(conn, memory, embedding)

        return SaveResult(
            memory_id=memory.id,
            scope=write_scope,
            tokens_stored=tokens,
        )

    async def recall(
        self,
        query: str,
        max_tokens: int = 200,
        scope: str | None = None,
        cwd: str = ".",
    ) -> RecallResult:
        scopes = [scope] if scope else self._scope_manager.resolve(cwd)
        query_embedding = self._embeddings.embed(query)

        candidates: list[tuple[str, float, str]] = []
        for s in scopes:
            conn = self._storage.get_database(s)
            results = self._repo.search_by_vector(conn, query_embedding, limit=20)
            for memory_id, score in results:
                candidates.append((memory_id, score, s))

        candidates.sort(key=lambda x: x[1], reverse=True)

        budget = TokenBudget(max_tokens=max_tokens)
        items: list[RecallItem] = []

        for memory_id, score, s in candidates:
            conn = self._storage.get_database(s)
            memory = self._repo.get(conn, memory_id)
            if memory is None:
                continue

            tokens = count_tokens(memory.content)
            if not budget.consume(tokens):
                break

            self._repo.update_accessed(conn, memory_id)
            items.append(
                RecallItem(
                    memory_id=memory.id,
                    content=memory.content,
                    score=score,
                    scope=memory.scope,
                    tags=memory.tags,
                    created_at=memory.created_at,
                )
            )

        return RecallResult(
            memories=items,
            total_tokens=budget.used_tokens,
            query=query,
        )

    def close(self) -> None:
        self._storage.close_all()
