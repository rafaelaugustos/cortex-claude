from __future__ import annotations

from pathlib import Path
from typing import Literal

from cortex_claude.core.scope_manager import ScopeManager
from cortex_claude.core.token_budget import TokenBudget
from cortex_claude.embeddings import EmbeddingEngine, count_tokens
from cortex_claude.facts import extract_facts
from cortex_claude.models.fact import Fact
from cortex_claude.models.memory import Memory, RecallItem, RecallResult, SaveResult
from cortex_claude.storage import FactRepository, MemoryRepository, StorageManager
from cortex_claude.summarizer import summarize

DEDUP_THRESHOLD = 0.92


class CortexEngine:
    def __init__(self, base_path: Path | None = None):
        self._base_path = base_path or Path.home() / ".cortex-claude"
        self._storage = StorageManager(self._base_path)
        self._embeddings = EmbeddingEngine()
        self._scope_manager = ScopeManager(self._base_path)
        self._memory_repo = MemoryRepository()
        self._fact_repo = FactRepository()

    async def save(
        self,
        content: str,
        tags: list[str] | None = None,
        scope: str | None = None,
        cwd: str = ".",
    ) -> SaveResult:
        write_scope = scope or self._scope_manager.get_write_scope(cwd)
        conn = self._storage.get_database(write_scope)

        embedding = self._embeddings.embed(content)
        tokens = count_tokens(content)

        existing = self._memory_repo.search_by_vector(conn, embedding, limit=1)
        if existing and existing[0][1] >= DEDUP_THRESHOLD:
            existing_memory = self._memory_repo.get(conn, existing[0][0])
            if existing_memory:
                merged = f"{existing_memory.content}\n\n{content}"
                self._memory_repo.delete(conn, existing_memory.id)
                content = merged
                embedding = self._embeddings.embed(content)
                tokens = count_tokens(content)

        summary = summarize(content) if tokens > 50 else None

        memory = Memory(
            content=content,
            summary=summary,
            tags=tags or [],
            scope=write_scope,
        )

        self._memory_repo.save(conn, memory, embedding)

        facts = extract_facts(content)
        for fact in facts:
            fact.source_memory_id = memory.id
            fact.scope = write_scope
        if facts:
            self._fact_repo.save_batch(conn, facts)

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
        depth: Literal["auto", "facts", "summaries", "full"] = "auto",
        cwd: str = ".",
    ) -> RecallResult:
        scopes = [scope] if scope else self._scope_manager.resolve(cwd)
        budget = TokenBudget(max_tokens=max_tokens)
        items: list[RecallItem] = []

        # Layer 1: Facts
        if depth in ("auto", "facts"):
            fact_items = self._recall_facts(scopes, query, budget)
            items.extend(fact_items)

            if depth == "facts" or (depth == "auto" and self._is_sufficient(items, budget)):
                return self._build_result(items, budget, query)

        # Layer 2: Summaries
        if depth in ("auto", "summaries"):
            summary_items = self._recall_summaries(scopes, query, budget)
            items.extend(summary_items)

            if depth == "summaries" or (depth == "auto" and self._is_sufficient(items, budget)):
                return self._build_result(items, budget, query)

        # Layer 3: Full chunks
        full_items = self._recall_chunks(scopes, query, budget)
        items.extend(full_items)

        return self._build_result(items, budget, query)

    async def get_facts(
        self,
        topic: str,
        relation: str | None = None,
        scope: str | None = None,
        limit: int = 20,
        cwd: str = ".",
    ) -> list[Fact]:
        scopes = [scope] if scope else self._scope_manager.resolve(cwd)
        all_facts: list[Fact] = []

        for s in scopes:
            conn = self._storage.get_database(s)
            facts = self._fact_repo.search(conn, topic, relation, limit)
            all_facts.extend(facts)

        all_facts.sort(key=lambda f: f.confidence, reverse=True)
        return all_facts[:limit]

    def _recall_facts(
        self,
        scopes: list[str],
        query: str,
        budget: TokenBudget,
    ) -> list[RecallItem]:
        items: list[RecallItem] = []
        query_embedding = self._embeddings.embed(query)
        seen_facts: set[str] = set()

        for s in scopes:
            conn = self._storage.get_database(s)

            # Find relevant memories via vector search, then get their facts
            vector_results = self._memory_repo.search_by_vector(conn, query_embedding, limit=5)
            for memory_id, score in vector_results:
                memory_facts = self._fact_repo.search_by_memory(conn, memory_id)
                for fact in memory_facts:
                    fact_key = f"{fact.subject}|{fact.relation}|{fact.object}"
                    if fact_key in seen_facts:
                        continue
                    seen_facts.add(fact_key)

                    text = f"{fact.subject} → {fact.relation} → {fact.object}"
                    tokens = count_tokens(text)
                    if not budget.consume(tokens):
                        return items
                    items.append(RecallItem(
                        memory_id=fact.source_memory_id,
                        content=text,
                        score=score + fact.confidence,
                        scope=fact.scope,
                        created_at=fact.created_at,
                    ))

            # Also search facts by keyword
            for word in query.lower().split():
                if len(word) < 3:
                    continue
                keyword_facts = self._fact_repo.search(conn, word, limit=5)
                for fact in keyword_facts:
                    fact_key = f"{fact.subject}|{fact.relation}|{fact.object}"
                    if fact_key in seen_facts:
                        continue
                    seen_facts.add(fact_key)

                    text = f"{fact.subject} → {fact.relation} → {fact.object}"
                    tokens = count_tokens(text)
                    if not budget.consume(tokens):
                        return items
                    items.append(RecallItem(
                        memory_id=fact.source_memory_id,
                        content=text,
                        score=fact.confidence,
                        scope=fact.scope,
                        created_at=fact.created_at,
                    ))

        return items

    def _recall_summaries(
        self,
        scopes: list[str],
        query: str,
        budget: TokenBudget,
    ) -> list[RecallItem]:
        items: list[RecallItem] = []
        query_embedding = self._embeddings.embed(query)

        seen_ids: set[str] = set()
        for s in scopes:
            conn = self._storage.get_database(s)
            results = self._memory_repo.search_by_vector(conn, query_embedding, limit=10)

            for memory_id, score in results:
                if memory_id in seen_ids:
                    continue
                seen_ids.add(memory_id)

                memory = self._memory_repo.get(conn, memory_id)
                if not memory or not memory.summary:
                    continue

                tokens = count_tokens(memory.summary)
                if not budget.consume(tokens):
                    return items

                self._memory_repo.update_accessed(conn, memory_id)
                items.append(RecallItem(
                    memory_id=memory.id,
                    content=memory.summary,
                    score=score,
                    scope=memory.scope,
                    tags=memory.tags,
                    created_at=memory.created_at,
                ))

        return items

    def _recall_chunks(
        self,
        scopes: list[str],
        query: str,
        budget: TokenBudget,
    ) -> list[RecallItem]:
        items: list[RecallItem] = []
        query_embedding = self._embeddings.embed(query)

        seen_ids: set[str] = set()
        for s in scopes:
            conn = self._storage.get_database(s)
            results = self._memory_repo.search_by_vector(conn, query_embedding, limit=10)

            for memory_id, score in results:
                if memory_id in seen_ids:
                    continue
                seen_ids.add(memory_id)

                memory = self._memory_repo.get(conn, memory_id)
                if not memory:
                    continue

                tokens = count_tokens(memory.content)
                if not budget.consume(tokens):
                    return items

                self._memory_repo.update_accessed(conn, memory_id)
                items.append(RecallItem(
                    memory_id=memory.id,
                    content=memory.content,
                    score=score,
                    scope=memory.scope,
                    tags=memory.tags,
                    created_at=memory.created_at,
                ))

        return items

    def _is_sufficient(self, items: list[RecallItem], budget: TokenBudget) -> bool:
        if not items:
            return False
        if budget.used_tokens >= budget.max_tokens * 0.6:
            return True
        avg_score = sum(i.score for i in items) / len(items)
        return len(items) >= 3 and avg_score > 0.7

    def _build_result(
        self,
        items: list[RecallItem],
        budget: TokenBudget,
        query: str,
    ) -> RecallResult:
        seen: dict[str, RecallItem] = {}
        for item in items:
            key = item.content
            if key not in seen or item.score > seen[key].score:
                seen[key] = item

        unique = sorted(seen.values(), key=lambda x: x.score, reverse=True)
        return RecallResult(
            memories=unique,
            total_tokens=budget.used_tokens,
            query=query,
        )

    def close(self) -> None:
        self._storage.close_all()
