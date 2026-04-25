from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cortex_claude.core.decay import recalculate_decay_scores
from cortex_claude.core.scope_manager import ScopeManager
from cortex_claude.core.token_budget import TokenBudget
from cortex_claude.embeddings import EmbeddingEngine, count_tokens
from cortex_claude.facts import extract_facts
from cortex_claude.models.fact import Fact
from cortex_claude.models.memory import Memory, RecallItem, RecallResult, SaveResult
from cortex_claude.server.config import CortexConfig
from cortex_claude.storage import FactRepository, MemoryRepository, StorageManager
from cortex_claude.summarizer import summarize


@dataclass
class ForgetResult:
    deleted: list[str]
    scope: str
    dry_run: bool


@dataclass
class StatusResult:
    scopes: list[dict]
    total_memories: int
    total_facts: int
    total_size_bytes: int


class CortexEngine:
    def __init__(self, base_path: Path | None = None, config: CortexConfig | None = None):
        self._config = config or CortexConfig.load(base_path)
        self._base_path = self._config.base_path
        self._storage = StorageManager(self._base_path)
        self._embeddings = EmbeddingEngine(model_name=self._config.embedding_model)
        self._scope_manager = ScopeManager(self._base_path)
        self._memory_repo = MemoryRepository()
        self._fact_repo = FactRepository()

    def initialize(self) -> None:
        for scope in self._storage.list_scopes():
            conn = self._storage.get_database(scope)
            recalculate_decay_scores(
                conn,
                decay_lambda=self._config.decay_lambda,
                min_score=self._config.decay_min_score,
            )

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
        if existing and existing[0][1] >= self._config.dedup_similarity_threshold:
            existing_memory = self._memory_repo.get(conn, existing[0][0])
            if existing_memory:
                merged = f"{existing_memory.content}\n\n{content}"
                self._fact_repo.delete_by_memory(conn, existing_memory.id)
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

        facts = extract_facts(
            content,
            min_confidence=self._config.fact_min_confidence,
            claude_fallback=self._config.fact_claude_fallback,
            claude_confidence_threshold=self._config.fact_claude_confidence_threshold,
        )
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

    async def traverse_graph(
        self,
        start: str,
        max_hops: int = 2,
        scope: str | None = None,
        cwd: str = ".",
    ) -> list[Fact]:
        scopes = [scope] if scope else self._scope_manager.resolve(cwd)
        visited: set[str] = set()
        result: list[Fact] = []
        frontier: list[str] = [start.lower()]

        for _ in range(max_hops):
            next_frontier: list[str] = []
            for entity in frontier:
                if entity in visited:
                    continue
                visited.add(entity)

                for s in scopes:
                    conn = self._storage.get_database(s)
                    facts = self._fact_repo.search(conn, entity, limit=20)
                    for fact in facts:
                        result.append(fact)
                        if fact.subject.lower() not in visited:
                            next_frontier.append(fact.subject.lower())
                        if fact.object.lower() not in visited:
                            next_frontier.append(fact.object.lower())

            frontier = next_frontier
            if not frontier:
                break

        seen: set[str] = set()
        unique: list[Fact] = []
        for f in result:
            key = f"{f.subject}|{f.relation}|{f.object}"
            if key not in seen:
                seen.add(key)
                unique.append(f)

        return unique

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

            # Vector search → find relevant memories → get their facts
            vector_results = self._memory_repo.search_by_vector(conn, query_embedding, limit=5)
            for memory_id, vec_score in vector_results:
                memory = self._memory_repo.get(conn, memory_id)
                decay = memory.decay_score if memory else 1.0

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
                        score=(vec_score + fact.confidence) * decay,
                        scope=fact.scope,
                        created_at=fact.created_at,
                    ))

            # FTS keyword search → find additional facts
            fts_ids = self._memory_repo.search_fts(conn, query, limit=5)
            for memory_id in fts_ids:
                memory = self._memory_repo.get(conn, memory_id)
                decay = memory.decay_score if memory else 1.0

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
                        score=fact.confidence * decay,
                        scope=fact.scope,
                        created_at=fact.created_at,
                    ))

            # Keyword search on fact table directly
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

            candidates = self._memory_repo.search_by_vector(conn, query_embedding, limit=10)

            # Merge with FTS results
            fts_ids = self._memory_repo.search_fts(conn, query, limit=5)
            fts_set = set(fts_ids)
            for fts_id in fts_ids:
                if not any(fts_id == c[0] for c in candidates):
                    candidates.append((fts_id, 0.5))

            for memory_id, score in candidates:
                if memory_id in seen_ids:
                    continue
                seen_ids.add(memory_id)

                memory = self._memory_repo.get(conn, memory_id)
                if not memory or not memory.summary:
                    continue

                adjusted_score = score * memory.decay_score
                if memory_id in fts_set:
                    adjusted_score += 0.2

                tokens = count_tokens(memory.summary)
                if not budget.consume(tokens):
                    return items

                self._memory_repo.update_accessed(conn, memory_id)
                items.append(RecallItem(
                    memory_id=memory.id,
                    content=memory.summary,
                    score=adjusted_score,
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

            candidates = self._memory_repo.search_by_vector(conn, query_embedding, limit=10)

            # Merge with FTS results
            fts_ids = self._memory_repo.search_fts(conn, query, limit=5)
            fts_set = set(fts_ids)
            for fts_id in fts_ids:
                if not any(fts_id == c[0] for c in candidates):
                    candidates.append((fts_id, 0.5))

            for memory_id, score in candidates:
                if memory_id in seen_ids:
                    continue
                seen_ids.add(memory_id)

                memory = self._memory_repo.get(conn, memory_id)
                if not memory:
                    continue

                adjusted_score = score * memory.decay_score
                if memory_id in fts_set:
                    adjusted_score += 0.2

                tokens = count_tokens(memory.content)
                if not budget.consume(tokens):
                    return items

                self._memory_repo.update_accessed(conn, memory_id)
                items.append(RecallItem(
                    memory_id=memory.id,
                    content=memory.content,
                    score=adjusted_score,
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
        return (
            len(items) >= 3
            and avg_score > self._config.sufficiency_confidence_threshold
        )

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

    async def forget(
        self,
        query: str | None = None,
        memory_id: str | None = None,
        scope: str | None = None,
        dry_run: bool = True,
        cwd: str = ".",
    ) -> ForgetResult:
        scopes = [scope] if scope else self._scope_manager.resolve(cwd)
        target_scope = scopes[0]
        to_delete: list[str] = []

        if memory_id:
            to_delete = [memory_id]
        elif query:
            query_embedding = self._embeddings.embed(query)
            for s in scopes:
                conn = self._storage.get_database(s)
                results = self._memory_repo.search_by_vector(conn, query_embedding, limit=5)
                for mid, score in results:
                    if score > 0.3:
                        to_delete.append(mid)
                        target_scope = s

        if not dry_run:
            for mid in to_delete:
                for s in scopes:
                    conn = self._storage.get_database(s)
                    memory = self._memory_repo.get(conn, mid)
                    if memory:
                        self._fact_repo.delete_by_memory(conn, mid)
                        self._memory_repo.delete(conn, mid)
                        target_scope = s
                        break

        return ForgetResult(deleted=to_delete, scope=target_scope, dry_run=dry_run)

    async def manage_scopes(
        self,
        action: str,
        name: str | None = None,
        path: str | None = None,
        cwd: str = ".",
    ) -> dict:
        if action == "list":
            scope_names = self._storage.list_scopes()
            infos = []
            for s in scope_names:
                conn = self._storage.get_database(s)
                mem_count = self._memory_repo.count(conn)
                fact_count = self._fact_repo.count(conn)
                db_path = self._storage.get_database_path(s)
                size = db_path.stat().st_size if db_path.exists() else 0
                infos.append({
                    "name": s,
                    "memories": mem_count,
                    "facts": fact_count,
                    "size_bytes": size,
                })
            return {"action": "list", "scopes": infos}

        elif action == "create" and name:
            self._storage.get_database(name)
            return {"action": "create", "scope": name, "status": "created"}

        elif action == "delete" and name:
            if name == "global":
                return {"action": "delete", "scope": name, "status": "cannot delete global scope"}
            self._storage.delete_scope(name)
            return {"action": "delete", "scope": name, "status": "deleted"}

        elif action == "link" and name and path:
            config_path = self._base_path / "config.json"
            config = {}
            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
            config.setdefault("scopes", {}).setdefault("mappings", {})[path] = name
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            self._scope_manager.reload()
            return {"action": "link", "path": path, "scope": name, "status": "linked"}

        elif action == "unlink" and path:
            config_path = self._base_path / "config.json"
            config = {}
            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
            mappings = config.get("scopes", {}).get("mappings", {})
            mappings.pop(path, None)
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            self._scope_manager.reload()
            return {"action": "unlink", "path": path, "status": "unlinked"}

        elif action == "info" and name:
            conn = self._storage.get_database(name)
            db_path = self._storage.get_database_path(name)
            return {
                "action": "info",
                "scope": name,
                "memories": self._memory_repo.count(conn),
                "facts": self._fact_repo.count(conn),
                "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
            }

        return {"action": action, "status": "invalid action or missing parameters"}

    async def status(self, scope: str | None = None, cwd: str = ".") -> StatusResult:
        scopes = [scope] if scope else self._storage.list_scopes()
        if not scopes:
            scopes = ["global"]

        scope_infos = []
        total_mem = 0
        total_facts = 0
        total_size = 0

        for s in scopes:
            conn = self._storage.get_database(s)
            mem_count = self._memory_repo.count(conn)
            fact_count = self._fact_repo.count(conn)
            db_path = self._storage.get_database_path(s)
            size = db_path.stat().st_size if db_path.exists() else 0

            scope_infos.append({
                "name": s,
                "memories": mem_count,
                "facts": fact_count,
                "size_bytes": size,
            })
            total_mem += mem_count
            total_facts += fact_count
            total_size += size

        return StatusResult(
            scopes=scope_infos,
            total_memories=total_mem,
            total_facts=total_facts,
            total_size_bytes=total_size,
        )

    async def run_decay(self, scope: str | None = None, cwd: str = ".") -> int:
        scopes = [scope] if scope else self._storage.list_scopes()
        total = 0
        for s in scopes:
            conn = self._storage.get_database(s)
            total += recalculate_decay_scores(
                conn,
                decay_lambda=self._config.decay_lambda,
                min_score=self._config.decay_min_score,
            )
        return total

    def close(self) -> None:
        self._storage.close_all()
