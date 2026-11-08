# Cortex Claude — Architecture & Technical Specification

> Intelligent, token-efficient, local-first memory system for Claude Code via MCP.

---

## Shared learning (current implementation)

`learning/` implements the observe → consolidate → retrieve → correct cycle. It is the default automatic-context path; the archive/code-graph architecture below remains available for explicit searches and reference storage.

One `learning.db` contains lessons, independent evidence, session budgets and delivery receipts. Origin is provenance, not a separate database. Personal observations become shared after `learning.confirmations` distinct sessions (default 3). Transferable lessons additionally require `learning.min_contexts` distinct origins (default 2). Context facts never become universal through repetition. Explicit user standing instructions bypass the confirmation threshold. Stable topic keys identify corrections; superseded notes are not retrieved or silently reactivated by old evidence.

The lightweight `UserPromptSubmit` handler recognizes direct EN/PT preferences. Nuanced observations come from the working assistant through `cortex_learn`, without a separate extraction-model call. `semantic.py` provides bounded Unix-socket calls to resident multilingual embeddings in the daemon. High-confidence similarity plus polarity, identifier, topic/origin and condition gates permit consolidation; ambiguous matches stay separate. Model-specific vectors are persisted and backfilled. A missing/slow model falls back to bilingual lexical matching. Runtime loading uses a local Hugging Face snapshot directory and does not download files.

Schema v2 adds conditional applicability, file SHA-256 snapshots, expiry, episode details, verified outcomes, progressive delivery receipts, main-transcript usage and task comparisons. The additive upgrade is transactional and keeps v1 lessons/evidence. Specific applicable preferences override generic ones; file changes/expiry move lessons to `stale`. Explicit corrections or a new successful episode verification are needed before reuse.

Schema v3 adds selection reasons, explicit usefulness feedback, conflict review, versioned work checkpoints and session-local file-read receipts. `selection.py` omits acknowledgements and compatible conclusions already present in a statement; questions still retrieve missing answers. Feedback is upserted per lesson/session, matched with hashed task cues and never changes evidence. Three negative votes can suppress similar-task retrieval. `conflicts.py` holds divergent preferences for an explicit choice or conditional correction; neither automatic nor detail retrieval bypasses review.

`reading.py` bounds UTF-8 reads to the repository, redacts private spans before caching and returns full/diff/unchanged responses within the requested budget. The cache is keyed by session, origin, path and range. Unknown/concurrent callers receive full content; compaction clears bases. Native editor read receipts cannot be manufactured by an MCP tool, so the assistant uses native Read directly when preparing an Edit. `tasks.py` stores at most 240 tokens of checkpoint fields in the same database, with origin matching, 14-day validity, dependency hashes and optimistic revision checks. Automatic resumption shares the ordinary context budget and abstains on ambiguous or stale checkpoints.

The dashboard uses Vue 3, Mavis Web/core 0.1.0-rc.12.1 and Jolt at the same release. Local SVG icons avoid the full icon font; archive/graph views load on demand. Mavis owns control semantics, dialogs, sheets and themes. Browser tests run the production bundle against the actual HTTP handlers with disposable databases. The localhost Host/Origin checks remain in force.

`experiences.py` stores situation/cause/solution. Successful recognized test runs create session/origin-bound receipts; a current receipt and the working assistant's association are needed to validate an episode. Test success proves only what those tests cover. Hypotheses are excluded from retrieval, and failed applications suspend reuse. Independent successful outcomes supply evidence. Detail reads preserve scope/conditions/freshness, are deduplicated and share the session budget with automatic context.

Automatic context is capped at 180 estimated tokens per prompt (96 for short/weak matches) and 600 per session including details. Compaction resets delivery receipts. `Stop` incrementally reads provider usage from the main transcript, retaining counters rather than content; repeated streaming message IDs use per-counter maxima. It handles partial writes and oversized records with bounded scans. Subagent usage and subscription limits are not inferred. Matched task reports preserve quality, token/cache counts, failures and time rather than presenting deduplication as total savings.

`hooks.py` imports neither PyTorch nor spaCy. SessionStart does no synchronous model work. PostToolUse records test receipts synchronously and keeps code indexing; raw capture is opt-in. Stop telemetry is asynchronous. Setup backs up configuration and preserves unrelated hooks/instructions.

`scripts/evaluate_learning.py` exercises the local lifecycle. `evaluate_semantic.py` exercises the resident model, socket and real prompt subprocesses. `evaluate_tasks.py` optionally runs the same isolated coding tasks through Claude with learning on/off and an independent grader. No synthetic lessons are seeded into the user's actual memory. Semantic similarity remains heuristic; lexical condition cues and tracked-file lists must be supplied accurately.

---

## Table of Contents

1. [Vision & Goals](#vision--goals)
2. [Core Concepts](#core-concepts)
3. [Architecture Overview](#architecture-overview)
4. [Data Model](#data-model)
5. [Storage Layer](#storage-layer)
6. [Memory Pipeline](#memory-pipeline)
7. [Retrieval Strategy — Progressive Recall](#retrieval-strategy--progressive-recall)
8. [Scope System](#scope-system)
9. [MCP Server Interface](#mcp-server-interface)
10. [Token Budget System](#token-budget-system)
11. [Embedding Engine](#embedding-engine)
12. [Fact Extraction (Knowledge Graph)](#fact-extraction-knowledge-graph)
13. [Summarization Layer](#summarization-layer)
14. [Project Structure & Packages](#project-structure--packages)
15. [Tech Stack](#tech-stack)
16. [Configuration](#configuration)
17. [Installation & Setup](#installation--setup)
18. [Performance Targets](#performance-targets)
19. [Roadmap](#roadmap)
20. [Glossary](#glossary)

---

## 1. Vision & Goals

### Problem

Current memory solutions for LLM assistants (like claude-mem) suffer from:

- **Token waste**: inject entire memory context into every prompt, regardless of relevance
- **No selectivity**: flat text dumps with keyword matching — no semantic understanding
- **No sharing**: memories are siloed per session with no cross-session or cross-project access
- **No intelligence**: no progressive retrieval, no summarization, no structured knowledge

### Solution

Cortex Claude is a **local-first MCP server** that provides Claude Code with intelligent, token-efficient memory through:

- **Progressive Recall**: 3-layer retrieval (facts → summaries → full chunks) that returns the minimum tokens needed
- **Knowledge Graph**: stores structured facts as subject-relation-object triplets, not just raw text
- **Configurable Scopes**: global, per-project, or custom scopes — user controls what's shared
- **On-Demand Access**: Claude calls memory tools only when needed — nothing is auto-injected
- **Local Performance**: everything runs locally — SQLite, local embeddings, zero network latency

### Design Principles

1. **Token efficiency above all** — every design decision optimizes for minimum token consumption
2. **Local-first** — no external APIs, no network calls, no cloud dependencies
3. **Progressive depth** — start shallow (facts), go deeper only when needed
4. **Zero configuration to start** — works out of the box, customizable when needed
5. **Open source & extensible** — MIT license, monorepo, pluggable architecture

---

## 2. Core Concepts

### Memory Unit

A Memory Unit is the atomic piece of information stored in Cortex. When content is saved, it is decomposed into:

```
┌─────────────────────────────────────────┐
│              Memory Unit                 │
├─────────────────────────────────────────┤
│  id: uuid                               │
│  content: string (original text)        │
│  summary: string (compressed version)   │
│  facts: Fact[] (extracted triplets)     │
│  embedding: float[] (vector)            │
│  tags: string[]                         │
│  scope: string                          │
│  created_at: timestamp                  │
│  accessed_at: timestamp                 │
│  access_count: number                   │
│  relevance_score: number (decays)       │
└─────────────────────────────────────────┘
```

### Fact (Knowledge Graph Triplet)

```
┌──────────────────────────────────┐
│             Fact                  │
├──────────────────────────────────┤
│  id: uuid                        │
│  subject: string                 │
│  relation: string                │
│  object: string                  │
│  confidence: number (0-1)        │
│  source_memory_id: uuid          │
│  scope: string                   │
│  created_at: timestamp           │
└──────────────────────────────────┘
```

Example facts:
```
("auth-service", "uses", "JWT")
("JWT tokens", "expire_after", "24 hours")
("user-model", "has_field", "email")
("project", "deploys_to", "AWS ECS")
("API", "rate_limited_at", "1000 req/min")
```

### Scope

A scope defines a boundary for memory isolation and sharing:

```
global          → accessible from everywhere
project:api     → only accessible when working in the API project
project:web     → only accessible when working in the Web project
custom:auth     → custom scope, manually assigned
```

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                    Claude Code                        │
│                                                      │
│  User asks question → Claude decides to recall memory │
│  Claude learns something → Claude decides to save     │
└──────────────┬───────────────────────────────────────┘
               │ MCP Protocol (stdio)
               ▼
┌──────────────────────────────────────────────────────┐
│              Cortex MCP Server                        │
│              (cortex_claude.server)                    │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │              Tool Router                        │  │
│  │  memory_save | memory_recall | memory_facts    │  │
│  │  memory_forget | memory_scopes                 │  │
│  └──────────┬─────────────────────────────────────┘  │
│             │                                        │
│  ┌──────────▼─────────────────────────────────────┐  │
│  │            Core Engine                          │  │
│  │         (cortex_claude.core)                     │  │
│  │                                                 │  │
│  │  ┌───────────┐ ┌───────────┐ ┌──────────────┐  │  │
│  │  │ Fact      │ │ Embedding │ │ Summarizer   │  │  │
│  │  │ Extractor │ │ Engine    │ │              │  │  │
│  │  └─────┬─────┘ └─────┬─────┘ └──────┬───────┘  │  │
│  │        │             │              │           │  │
│  │  ┌─────▼─────────────▼──────────────▼────────┐  │  │
│  │  │          Scope Manager                     │  │  │
│  │  │   resolves which DBs to query/write        │  │  │
│  │  └─────────────────┬──────────────────────────┘  │  │
│  │                    │                             │  │
│  └────────────────────┼─────────────────────────────┘  │
│                       │                                │
│  ┌────────────────────▼─────────────────────────────┐  │
│  │           Storage Layer                           │  │
│  │         (cortex_claude.storage)                    │  │
│  │                                                   │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────────────┐   │  │
│  │  │ Facts   │  │ Chunks  │  │ Summaries       │   │  │
│  │  │ Table   │  │ Table   │  │ Table           │   │  │
│  │  │ (graph) │  │ + vec   │  │                 │   │  │
│  │  └─────────┘  └─────────┘  └─────────────────┘   │  │
│  │                                                   │  │
│  │  SQLite + sqlite-vec (per scope)                  │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘

File System:
~/.cortex-claude/
├── config.json
├── global.db
└── scopes/
    ├── project__api.db
    ├── project__web.db
    └── custom__auth.db
```

---

## 4. Data Model

### SQLite Schema

Each scope database (`.db` file) contains the following tables:

```sql
-- Core memory units
CREATE TABLE memories (
    id TEXT PRIMARY KEY,             -- UUID v7 (sortable by time)
    content TEXT NOT NULL,           -- original text
    summary TEXT,                    -- compressed version
    embedding BLOB,                 -- float32 vector from local model
    tags TEXT,                       -- JSON array of tags
    scope TEXT NOT NULL,             -- scope identifier
    created_at INTEGER NOT NULL,     -- unix timestamp ms
    updated_at INTEGER NOT NULL,     -- unix timestamp ms
    accessed_at INTEGER NOT NULL,    -- last retrieval timestamp
    access_count INTEGER DEFAULT 0,  -- number of times retrieved
    decay_score REAL DEFAULT 1.0     -- relevance decay (0.0 - 1.0)
);

-- Knowledge graph facts (triplets)
CREATE TABLE facts (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    relation TEXT NOT NULL,
    object TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,     -- extraction confidence
    source_memory_id TEXT NOT NULL,  -- which memory this came from
    scope TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (source_memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

-- Vector index for semantic search (sqlite-vec)
CREATE VIRTUAL TABLE memory_vectors USING vec0(
    id TEXT PRIMARY KEY,
    embedding float[384]             -- all-MiniLM-L6-v2 output dimension
);

-- Indexes for fast retrieval
CREATE INDEX idx_facts_subject ON facts(subject);
CREATE INDEX idx_facts_object ON facts(object);
CREATE INDEX idx_facts_relation ON facts(relation);
CREATE INDEX idx_facts_subject_relation ON facts(subject, relation);
CREATE INDEX idx_memories_scope ON memories(scope);
CREATE INDEX idx_memories_tags ON memories(tags);
CREATE INDEX idx_memories_accessed ON memories(accessed_at);
CREATE INDEX idx_memories_decay ON memories(decay_score);

-- Full-text search on memory content
CREATE VIRTUAL TABLE memories_fts USING fts5(
    content,
    summary,
    tags,
    content='memories',
    content_rowid='rowid'
);
```

### Decay Score Algorithm

Memories lose relevance over time unless accessed. This prevents stale memories from polluting results.

```
decay_score = base_score * e^(-lambda * days_since_access) * log(1 + access_count)

Where:
  base_score   = 1.0 (initial)
  lambda       = 0.05 (configurable decay rate)
  days_since_access = (now - accessed_at) / 86400000
  access_count = number of times retrieved
```

A background job recalculates decay scores periodically (on server start and every 6 hours).

---

## 5. Storage Layer

### Package: `cortex_claude.storage`

Responsibilities:
- Manage SQLite connections per scope
- Handle sqlite-vec virtual tables
- CRUD operations for memories and facts
- Vector similarity search
- Full-text search
- Decay score management

### Database Per Scope

Each scope gets its own SQLite file. This provides:

- **Isolation**: deleting a scope = deleting a file
- **Performance**: smaller databases = faster queries
- **Portability**: copy a `.db` file to share a scope
- **Concurrency**: no cross-scope locking

### Connection Pool

```python
class StorageManager:
    def get_database(self, scope: str) -> Database:
        """Get or create a SQLite connection for the given scope."""
        ...

    def list_scopes(self) -> list[str]:
        """List all available scopes."""
        ...

    def delete_scope(self, scope: str) -> None:
        """Delete a scope and its database file."""
        ...

    def get_database_path(self, scope: str) -> Path:
        """Return the file path for a scope's database."""
        ...

    def vacuum(self, scope: str) -> None:
        """Reclaim unused space in a scope's database."""
        ...
```

SQLite is opened in WAL mode for concurrent reads during writes.

---

## 6. Memory Pipeline

### Save Pipeline

When `memory_save` is called, the following pipeline executes:

```
Input: { content, tags?, scope? }
           │
           ▼
    ┌──────────────┐
    │ 1. Normalize  │  Clean whitespace, detect language
    │    Content    │
    └──────┬───────┘
           │
     ┌─────▼───────┐
     │ 2. Generate  │  Local model: all-MiniLM-L6-v2
     │   Embedding  │  Output: float[384]
     └──────┬───────┘
            │
     ┌──────▼────────┐
     │ 3. Extract    │  NLP-based local extraction
     │    Facts      │  Output: Fact[] triplets
     └──────┬────────┘
            │
     ┌──────▼────────┐
     │ 4. Generate   │  Extractive summarization (local)
     │    Summary    │  Target: <25% of original tokens
     └──────┬────────┘
            │
     ┌──────▼────────┐
     │ 5. Deduplicate│  Check if similar memory exists
     │               │  Cosine similarity > 0.92 = merge
     └──────┬────────┘
            │
     ┌──────▼────────┐
     │ 6. Store      │  Write to correct scope DB
     │               │  memory + facts + vector + FTS
     └──────────────┘
```

### Deduplication Strategy

Before storing, we check for near-duplicates:

1. Compute embedding of new content
2. Search existing vectors with cosine similarity threshold `>= 0.92`
3. If match found:
   - **Merge**: update existing memory with new content appended
   - **Re-extract**: regenerate facts and summary
   - **Update timestamp**: refresh `updated_at` and `accessed_at`
4. If no match: insert as new memory

This prevents memory bloat from repeated saves of similar content.

---

## 7. Retrieval Strategy — Progressive Recall

This is the **core innovation** of Cortex Claude. Instead of dumping everything, we retrieve progressively, starting from the most token-efficient source.

### The 3 Layers

```
┌─────────────────────────────────────────────────────────┐
│                  Progressive Recall                       │
│                                                          │
│  Layer 1: FACTS (Knowledge Graph)                        │
│  ─────────────────────────────────                       │
│  Cost: ~5-15 tokens per fact                             │
│  Speed: <5ms (index lookup)                              │
│  When: ALWAYS tried first                                │
│  How: Match query against subject/object/relation        │
│       using FTS + embedding similarity on fact text       │
│  Returns: Structured triplets                            │
│                                                          │
│  Example output (3 facts = ~40 tokens):                  │
│    auth-service → uses → JWT                             │
│    JWT tokens → expire_after → 24 hours                  │
│    auth-service → middleware → express-jwt                │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ If facts are sufficient (high confidence + coverage) │ │
│  │ → STOP HERE. Return facts only.                      │ │
│  └────────────────────────┬────────────────────────────┘ │
│                           │ Not enough?                   │
│                           ▼                               │
│  Layer 2: SUMMARIES                                      │
│  ─────────────────                                       │
│  Cost: ~50-150 tokens per summary                        │
│  Speed: <15ms (FTS + vector search)                      │
│  When: Facts didn't fully answer the query               │
│  How: Semantic search on summary embeddings              │
│  Returns: Compressed text summaries                      │
│                                                          │
│  Example output (~120 tokens):                           │
│    "The auth service uses JWT with 24h expiry.           │
│     Tokens are validated via express-jwt middleware.      │
│     Refresh tokens are stored in httpOnly cookies        │
│     with 7-day expiry. Rate limited to 10 auth           │
│     attempts per minute per IP."                         │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ If summaries are sufficient                          │ │
│  │ → STOP HERE. Return facts + summaries.               │ │
│  └────────────────────────┬────────────────────────────┘ │
│                           │ Still not enough?             │
│                           ▼                               │
│  Layer 3: FULL CHUNKS                                    │
│  ────────────────────                                    │
│  Cost: ~200-2000 tokens per chunk                        │
│  Speed: <30ms (vector search)                            │
│  When: Need full detail/context                          │
│  How: Top-K vector similarity search on full content     │
│  Returns: Original stored text                           │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Sufficiency Heuristic

How does the system decide when to stop?

```python
@dataclass
class RecallResult:
    facts: list[Fact]
    summaries: list[Summary]
    chunks: list[Chunk]
    layer_reached: Literal[1, 2, 3]
    total_tokens: int
    confidence: float

def is_layer_sufficient(
    query: str,
    results: RecallResult,
    max_tokens: int,
) -> bool:
    # 1. Coverage: do the results cover the key entities in the query?
    query_coverage = compute_entity_coverage(query, results)

    # 2. Confidence: how confident are we in the results?
    avg_confidence = compute_average_confidence(results)

    # 3. Token budget: have we hit the caller's max_tokens?
    within_budget = results.total_tokens <= max_tokens

    return query_coverage > 0.7 and avg_confidence > 0.6 and within_budget
```

### Token Counting

We use a fast local tokenizer (tiktoken-compatible) to count tokens before returning results. The system never exceeds the caller's `max_tokens` budget.

---

## 8. Scope System

### Package: `cortex_claude.core` (ScopeManager)

### Scope Resolution

When the MCP server starts, it receives the current working directory from Claude Code. The ScopeManager resolves which scopes to use:

```python
class ScopeManager:
    def resolve(self, cwd: str) -> list[str]:
        """Resolve active scopes for a given working directory."""
        ...

    def create(self, name: str, paths: list[str] | None = None) -> None:
        """Create a new scope, optionally linked to directories."""
        ...

    def delete(self, name: str) -> None:
        """Delete a scope and its database."""
        ...

    def list(self) -> list[ScopeInfo]:
        """List all available scopes."""
        ...

    def link(self, path: str, scope: str) -> None:
        """Link a directory to a scope."""
        ...

    def unlink(self, path: str) -> None:
        """Unlink a directory from a scope."""
        ...
```

### Resolution Algorithm

```
Input: cwd = "/Users/rafael/projects/api"

1. Check config.json for explicit path mappings
   → Found: "/Users/rafael/projects/api" → "project:api"

2. Always include "global" scope

3. Return: ["project:api", "global"]

Search order: project scope first, then global
Write default: project scope (if exists), else global
```

### Multi-Scope Queries

When querying across multiple scopes, results are merged and ranked:

```
project:api results  ──┐
                       ├──→  Merge & Rank by:
global results       ──┘     1. Relevance score (embedding similarity)
                              2. Decay score
                              3. Scope priority (project > global)
                              4. Token budget
```

---

## 9. MCP Server Interface

### Package: `cortex_claude.server`

The MCP server exposes the following tools to Claude Code:

### `cortex_save`

Saves a memory unit with automatic fact extraction, embedding, and summarization.

```python
@server.tool()
async def cortex_save(
    content: str,          # The information to remember
    tags: list[str] = [],  # Optional tags for categorization
    scope: str | None = None,  # Optional scope override (default: current project)
) -> SaveResult:
    """Save information to persistent memory.

    Automatically extracts structured facts, generates searchable
    embeddings, and creates compressed summaries. Use 'global' scope
    for cross-project memories.
    """
    ...
```

### `cortex_recall`

Retrieves relevant memories using progressive recall (facts → summaries → chunks).

```python
@server.tool()
async def cortex_recall(
    query: str,                           # What you want to remember
    max_tokens: int = 200,                # Token budget for the response
    scope: str | None = None,             # Optional scope filter
    depth: Literal["auto", "facts", "summaries", "full"] = "auto",
) -> RecallResult:
    """Recall relevant memories using progressive retrieval.

    Starts with compact facts (minimal tokens), escalates to summaries,
    then full content only if needed. Respects token budget.
    - depth='facts': only graph triplets (~5-15 tokens each)
    - depth='summaries': facts + compressed summaries
    - depth='full': all layers including original content
    - depth='auto': progressive, stops when sufficient (default)
    """
    ...
```

### `cortex_facts`

Direct access to the knowledge graph. Ultra-low token cost.

```python
@server.tool()
async def cortex_facts(
    topic: str,                    # Entity or topic to look up
    relation: str | None = None,   # Filter by relation type
    scope: str | None = None,      # Optional scope filter
    limit: int = 20,               # Max facts to return
) -> list[Fact]:
    """Query the knowledge graph directly.

    Returns structured subject-relation-object triplets.
    Extremely token-efficient (~5-15 tokens per fact).
    """
    ...
```

### `cortex_forget`

Removes memories matching a query or filter.

```python
@server.tool()
async def cortex_forget(
    query: str | None = None,       # Natural language description of what to forget
    memory_id: str | None = None,   # Specific memory ID to delete
    scope: str | None = None,       # Only forget within this scope
    dry_run: bool = True,           # Preview what would be deleted
) -> ForgetResult:
    """Remove memories. Use to delete outdated or incorrect information.

    Default is dry_run=True (preview only). Set dry_run=False to actually delete.
    """
    ...
```

### `cortex_scopes`

Manage memory scopes.

```python
@server.tool()
async def cortex_scopes(
    action: Literal["list", "create", "delete", "link", "unlink", "info"],
    name: str | None = None,   # Scope name (for create/delete/info)
    path: str | None = None,   # Directory path (for link/unlink)
) -> ScopeResult:
    """List, create, or manage memory scopes.

    Scopes control memory isolation and sharing between projects.
    """
    ...
```

### `cortex_status`

Debug and stats tool.

```python
@server.tool()
async def cortex_status(
    scope: str | None = None,  # Stats for specific scope only
) -> StatusResult:
    """Show Cortex memory statistics.

    Returns: total memories, facts count, scopes, storage size, health info.
    """
    ...
```

---

## 10. Token Budget System

The token budget system is what makes Cortex dramatically more efficient than alternatives.

### How It Works

```python
@dataclass
class TokenBudget:
    max_tokens: int          # caller's budget (default: 200)
    used_tokens: int = 0     # tokens consumed so far

    @property
    def remaining(self) -> int:
        return self.max_tokens - self.used_tokens

    # Allocation strategy (percentage of max)
    facts_ratio: float = 0.40      # 40% of max by default
    summaries_ratio: float = 0.35  # 35% of max by default
    chunks_ratio: float = 0.25     # 25% of max by default

    @property
    def facts_budget(self) -> int:
        return int(self.max_tokens * self.facts_ratio)

    @property
    def summaries_budget(self) -> int:
        return int(self.max_tokens * self.summaries_ratio)

    @property
    def chunks_budget(self) -> int:
        return int(self.max_tokens * self.chunks_ratio)
```

### Budget Allocation

```
max_tokens = 200 (default)

Step 1: Retrieve facts
  → Found 5 facts = ~60 tokens
  → 60 < 200, continue? Check sufficiency.
  → Coverage: 0.8, Confidence: 0.7 → SUFFICIENT
  → Return facts only. Total: 60 tokens.

────────────────────────────────────────

max_tokens = 500 (explicit request)

Step 1: Retrieve facts
  → Found 3 facts = ~35 tokens
  → Coverage: 0.4 → NOT SUFFICIENT
Step 2: Retrieve summaries
  → Found 2 summaries = ~180 tokens
  → Total: 215 tokens. Coverage: 0.85 → SUFFICIENT
  → Return facts + summaries. Total: 215 tokens.

────────────────────────────────────────

max_tokens = 2000 (need full detail)

Step 1: facts → 40 tokens, coverage 0.3
Step 2: summaries → 160 tokens, coverage 0.6
Step 3: chunks → 800 tokens, coverage 0.95
→ Return all layers. Total: 1000 tokens.
```

### Token Estimation

We use a fast local tokenizer for accurate token counting:

```python
import tiktoken

_encoder = tiktoken.get_encoding("cl100k_base")

def estimate_tokens(text: str) -> int:
    """Fast, accurate token count compatible with Claude's tokenizer."""
    return len(_encoder.encode(text))
```

---

## 11. Embedding Engine

### Package: `cortex_claude.embeddings`

### Model: `all-MiniLM-L6-v2`

- **Dimensions**: 384
- **Size**: ~80MB (via sentence-transformers, auto-cached by HuggingFace)
- **Speed**: <10ms per embedding on CPU
- **Quality**: excellent for semantic similarity tasks
- **License**: Apache 2.0

### Why Local Embeddings?

1. **Zero latency**: no network round-trip
2. **Zero cost**: no API charges
3. **Privacy**: content never leaves the machine
4. **Reliability**: works offline

### Implementation

```python
from sentence_transformers import SentenceTransformer
import numpy as np

class EmbeddingEngine:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> np.ndarray:
        """Generate embedding for a single text. Returns float32[384]."""
        return self._model.encode(text, normalize_embeddings=True)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Batch embed for efficiency. Returns float32[N, 384]."""
        return self._model.encode(texts, normalize_embeddings=True, batch_size=32)

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two embeddings (already normalized)."""
        return float(np.dot(a, b))
```

Uses `sentence-transformers` which wraps HuggingFace models with optimized inference. Model is downloaded on first run and cached in `~/.cache/huggingface/` (standard HF cache).

---

## 12. Fact Extraction (Knowledge Graph)

### Strategy: spaCy NLP + Pattern Matching (Zero Token Cost)

We use **spaCy** for fact extraction — it runs 100% locally, costs zero tokens, and provides high-quality linguistic analysis (dependency parsing, NER, POS tagging). This is a key advantage of choosing Python.

### Why spaCy?

| Feature | Benefit for Cortex |
|---------|-------------------|
| **Dependency parsing** | Extracts subject-verb-object triples from any sentence structure |
| **Named Entity Recognition (NER)** | Identifies people, orgs, tech, dates — better entity normalization |
| **POS tagging** | Understands grammar to produce accurate relations |
| **Multiple languages** | Supports EN, PT, ES, DE, FR, etc. out of the box |
| **Speed** | ~10K sentences/sec on CPU with `en_core_web_sm` |
| **Size** | `en_core_web_sm` is ~12MB, `en_core_web_md` is ~40MB |

### Method 1: spaCy Dependency Parsing (Primary)

Extracts SVO (Subject-Verb-Object) triples using spaCy's dependency tree:

```python
import spacy

nlp = spacy.load("en_core_web_sm")

def extract_facts_spacy(text: str) -> list[Fact]:
    """Extract structured facts using spaCy dependency parsing."""
    doc = nlp(text)
    facts = []

    for sent in doc.sents:
        # Find the root verb of the sentence
        root = sent.root

        if root.pos_ != "VERB":
            continue

        # Extract subject (nsubj, nsubjpass)
        subjects = [
            child for child in root.children
            if child.dep_ in ("nsubj", "nsubjpass")
        ]

        # Extract object (dobj, attr, prep + pobj)
        objects = [
            child for child in root.children
            if child.dep_ in ("dobj", "attr", "pobj")
        ]

        # Also capture prepositional objects: "deploys to AWS"
        for child in root.children:
            if child.dep_ == "prep":
                for grandchild in child.children:
                    if grandchild.dep_ == "pobj":
                        objects.append(grandchild)

        # Build facts from all subject-object combinations
        for subj in subjects:
            subj_span = get_compound_span(subj)  # "auth service" not just "service"
            for obj in objects:
                obj_span = get_compound_span(obj)
                facts.append(Fact(
                    subject=normalize_entity(subj_span),
                    relation=normalize_relation(root.lemma_),
                    object=normalize_entity(obj_span),
                    confidence=0.8,
                ))

    return facts


def get_compound_span(token) -> str:
    """Expand a token to include its compound modifiers.

    'auth' + 'service' → 'auth service'
    """
    compounds = [
        child.text for child in token.children
        if child.dep_ in ("compound", "amod")
    ]
    return " ".join(compounds + [token.text])
```

**Example input:**
> "The auth service uses JWT with 24-hour expiry and stores refresh tokens in httpOnly cookies"

**Extracted facts:**
```
(auth service, use, JWT)              confidence: 0.8
(auth service, store, refresh tokens) confidence: 0.8
(refresh tokens, in, httpOnly cookies) confidence: 0.7
(JWT, with, 24-hour expiry)           confidence: 0.7
```

### Method 2: spaCy NER + Pattern Matching (Complementary)

Named Entity Recognition catches structured facts that SVO parsing might miss:

```python
def extract_facts_ner(text: str) -> list[Fact]:
    """Extract facts from named entities and their context."""
    doc = nlp(text)
    facts = []

    for ent in doc.ents:
        # Entity type becomes a relation
        if ent.label_ in ("ORG", "PRODUCT", "GPE", "TECH"):
            # Look at the verb connecting this entity
            verb = find_governing_verb(ent.root)
            if verb:
                subject = find_subject_of(verb)
                if subject:
                    facts.append(Fact(
                        subject=normalize_entity(subject),
                        relation=verb.lemma_,
                        object=normalize_entity(ent.text),
                        confidence=0.75,
                    ))

        # Numeric entities → property facts
        if ent.label_ in ("CARDINAL", "QUANTITY", "TIME", "PERCENT"):
            context_noun = find_closest_noun(ent)
            if context_noun:
                facts.append(Fact(
                    subject=normalize_entity(context_noun),
                    relation="has_value",
                    object=ent.text,
                    confidence=0.7,
                ))

    return facts
```

### Method 3: Regex Patterns (Fallback)

For very structured text that spaCy might parse awkwardly (config values, key-value pairs, etc.):

```python
FACT_PATTERNS = [
    # "X: Y" or "X = Y" (config-style)
    re.compile(r"(\w[\w\s-]+?):\s+(.+?)(?:\.|$)", re.MULTILINE),
    # "X is set to Y"
    re.compile(r"(\w[\w\s-]+?)\s+(?:is set to|defaults to|equals)\s+(.+?)(?:\.|$)", re.I),
    # "rate limit: 1000 req/min"
    re.compile(r"(rate.?limit)\w*:\s*(\d+\s*\w+)", re.I),
]
```

### Extraction Pipeline

All three methods run together and results are merged + deduplicated:

```python
def extract_all_facts(text: str) -> list[Fact]:
    """Run all extraction methods and merge results."""
    facts = []

    # Primary: spaCy dependency parsing
    facts.extend(extract_facts_spacy(text))

    # Complementary: NER-based
    facts.extend(extract_facts_ner(text))

    # Fallback: pattern matching
    facts.extend(extract_facts_patterns(text))

    # Deduplicate by (subject, relation, object) similarity
    facts = deduplicate_facts(facts)

    # Filter by confidence threshold
    return [f for f in facts if f.confidence >= config.min_confidence]
```

### Claude-Assisted Extraction (Optional, Opt-In)

Users can opt-in to Claude-assisted extraction in `config.json`. This costs tokens but produces the highest quality facts. **Default is off.**

```json
{
    "facts": {
        "extraction_method": "local",
        "claude_fallback": false,
        "claude_confidence_threshold": 0.5
    }
}
```

When `claude_fallback: true`, Claude is only called if spaCy extraction produces fewer than 2 facts with confidence > 0.6. This minimizes token cost while handling edge cases.

---

## 13. Summarization Layer

### Strategy: Extractive + Compression

Instead of using an LLM for summarization (token cost), we use local extractive summarization:

### Algorithm

```python
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer

def summarize(content: str, target_ratio: float = 0.25) -> str:
    """Extractive summarization using spaCy + TF-IDF scoring.

    Selects the most important original sentences to produce a
    summary at ~25% of original token count. Zero API calls.
    """
    doc = nlp(content)
    sentences = list(doc.sents)

    if len(sentences) <= 2:
        return content  # Already short enough

    # Score each sentence
    scored = []
    for i, sent in enumerate(sentences):
        score = (
            position_score(i, len(sentences))       # First sentences matter more
            + entity_density_score(sent)             # Sentences with entities are important
            + tfidf_score(sent.text, content)        # Statistically important words
            + embedding_similarity_score(sent.text, content)  # Semantic relevance
        )
        scored.append((i, sent.text, score))

    # Select top sentences within token budget
    target_tokens = int(estimate_tokens(content) * target_ratio)
    scored.sort(key=lambda x: x[2], reverse=True)

    selected = []
    used_tokens = 0
    for idx, text, score in scored:
        tokens = estimate_tokens(text)
        if used_tokens + tokens <= target_tokens:
            selected.append((idx, text))
            used_tokens += tokens

    # Return in original order
    selected.sort(key=lambda x: x[0])
    return " ".join(text for _, text in selected)


def entity_density_score(sent) -> float:
    """Higher score for sentences with more named entities."""
    ent_count = len(sent.ents)
    return min(ent_count * 0.15, 0.5)


def position_score(index: int, total: int) -> float:
    """First and last sentences score higher."""
    if index == 0:
        return 0.3
    if index == total - 1:
        return 0.15
    return 0.0
```

This produces summaries at ~25% of original token count with no API calls. spaCy's sentence segmentation and NER make the scoring more accurate than pure regex-based approaches.

---

## 14. Project Structure & Packages

### Project Structure

```
cortex-claude/
├── pyproject.toml                # Project config (PEP 621) + dependencies
├── uv.lock                       # Lock file (uv package manager)
├── ARCHITECTURE.md               # This file
├── README.md                     # User-facing docs
├── LICENSE                       # MIT
│
├── src/
│   └── cortex_claude/            # Main package
│       ├── __init__.py
│       ├── __main__.py           # Entry point: python -m cortex_claude
│       │
│       ├── core/                 # Core engine & orchestration
│       │   ├── __init__.py
│       │   ├── engine.py         # Main orchestrator
│       │   ├── scope_manager.py  # Scope resolution & management
│       │   ├── token_budget.py   # Token budget system
│       │   └── decay.py          # Decay score calculator
│       │
│       ├── pipeline/             # Save & recall pipelines
│       │   ├── __init__.py
│       │   ├── save.py           # Save pipeline (embed → extract → summarize → store)
│       │   └── recall.py         # Progressive recall (facts → summaries → chunks)
│       │
│       ├── storage/              # SQLite + sqlite-vec persistence
│       │   ├── __init__.py
│       │   ├── database.py       # Connection manager (per-scope DBs)
│       │   ├── migrations.py     # Schema migrations
│       │   ├── memory_repo.py    # Memory CRUD
│       │   ├── fact_repo.py      # Fact/graph CRUD
│       │   └── vector_repo.py    # Vector similarity search
│       │
│       ├── embeddings/           # Local embedding engine
│       │   ├── __init__.py
│       │   ├── engine.py         # sentence-transformers wrapper
│       │   └── tokenizer.py      # tiktoken token counter
│       │
│       ├── facts/                # Fact extraction (spaCy)
│       │   ├── __init__.py
│       │   ├── extractor.py      # Extraction orchestrator (spaCy + patterns)
│       │   ├── spacy_extract.py  # spaCy dependency parsing & NER
│       │   ├── patterns.py       # Regex-based fallback patterns
│       │   └── normalizer.py     # Entity & relation normalization
│       │
│       ├── summarizer/           # Extractive summarization
│       │   ├── __init__.py
│       │   ├── extractive.py     # Sentence scoring & selection
│       │   └── scoring.py        # TF-IDF, position, entity density
│       │
│       ├── server/               # MCP server (entry point)
│       │   ├── __init__.py
│       │   ├── app.py            # MCP server bootstrap & tool registration
│       │   ├── tools/
│       │   │   ├── __init__.py
│       │   │   ├── save.py
│       │   │   ├── recall.py
│       │   │   ├── facts.py
│       │   │   ├── forget.py
│       │   │   ├── scopes.py
│       │   │   └── status.py
│       │   └── config.py         # Configuration loader
│       │
│       └── models/               # Pydantic models & dataclasses
│           ├── __init__.py
│           ├── memory.py         # MemoryUnit, SaveResult, RecallResult
│           ├── fact.py           # Fact, FactQuery
│           └── scope.py          # ScopeInfo, ScopeConfig
│
├── tests/
│   ├── conftest.py               # Shared fixtures
│   ├── unit/
│   │   ├── test_facts.py
│   │   ├── test_embeddings.py
│   │   ├── test_summarizer.py
│   │   ├── test_token_budget.py
│   │   └── test_decay.py
│   ├── integration/
│   │   ├── test_save_pipeline.py
│   │   ├── test_recall_pipeline.py
│   │   └── test_storage.py
│   └── fixtures/
│       └── sample_memories.json
│
└── scripts/
    ├── setup.py                  # First-run setup (download models)
    └── benchmark.py              # Performance benchmarks
```

---

## 15. Tech Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| **Language** | Python 3.11+ | Best ML/NLP ecosystem, native spaCy/sentence-transformers support |
| **Package Manager** | uv | Fast, modern Python package manager (Rust-based) |
| **Database** | sqlite3 (stdlib) + sqlite-vec | Zero-dependency SQLite, vec extension for vectors |
| **Vector Search** | sqlite-vec | SQLite extension, no separate service needed |
| **Embeddings** | sentence-transformers + all-MiniLM-L6-v2 | Local, fast, first-class Python support |
| **NLP / Facts** | spaCy (en_core_web_sm) | Dependency parsing, NER, SVO extraction — ~12MB model |
| **Summarization** | spaCy + scikit-learn (TF-IDF) | Extractive summarization, no LLM needed |
| **Token Counting** | tiktoken | Fast, accurate, cl100k_base (Claude-compatible) |
| **MCP SDK** | mcp (official Python SDK) | Official MCP Python SDK by Anthropic |
| **Data Models** | Pydantic v2 | Validation, serialization, type safety |
| **Test** | pytest + pytest-asyncio | Standard Python testing, async support |
| **Type Checking** | pyright / mypy | Static type checking for correctness |

---

## 16. Configuration

### File: `~/.cortex-claude/config.json`

```json
{
    "version": 1,

    "storage": {
        "path": "~/.cortex-claude",
        "max_db_size_mb": 500
    },

    "scopes": {
        "mappings": {
            "/Users/rafael/projects/api": "project:api",
            "/Users/rafael/projects/web": "project:web"
        },
        "default": "global",
        "search_order": "project_first"
    },

    "recall": {
        "default_max_tokens": 200,
        "default_depth": "auto",
        "sufficiency": {
            "coverage_threshold": 0.7,
            "confidence_threshold": 0.6
        }
    },

    "embeddings": {
        "model": "all-MiniLM-L6-v2",
        "model_path": "~/.cortex-claude/models",
        "batch_size": 32
    },

    "facts": {
        "extraction_method": "local",
        "min_confidence": 0.5
    },

    "decay": {
        "lambda": 0.05,
        "recalculate_interval_hours": 6,
        "min_score": 0.01
    },

    "deduplication": {
        "similarity_threshold": 0.92,
        "merge_strategy": "append"
    }
}
```

### Claude Code MCP Configuration

Add to `~/.claude/claude_code_config.json`:

```json
{
    "mcpServers": {
        "cortex": {
            "command": "uvx",
            "args": ["cortex-claude"],
            "env": {
                "CORTEX_HOME": "~/.cortex-claude"
            }
        }
    }
}
```

Alternative (if installed via pip):

```json
{
    "mcpServers": {
        "cortex": {
            "command": "python",
            "args": ["-m", "cortex_claude"],
            "env": {
                "CORTEX_HOME": "~/.cortex-claude"
            }
        }
    }
}
```

---

## 17. Installation & Setup

### Quick Start

```bash
# Install via uvx (recommended — runs in isolated env)
uvx cortex-claude setup

# Or install via pip
pip install cortex-claude

# First run — downloads spaCy model (~12MB) + embedding model (~80MB)
cortex-claude setup

# Or just add to Claude Code config (auto-setup on first MCP call)
```

### Development Setup

```bash
git clone https://github.com/your-user/cortex-claude.git
cd cortex-claude

# Install dependencies with uv
uv sync

# Download required models
uv run python -m spacy download en_core_web_sm

# Run tests
uv run pytest

# Run MCP server locally for testing
uv run python -m cortex_claude

# Run with stdio (how Claude Code will call it)
uv run python -m cortex_claude --transport stdio
```

---

## 18. Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| `cortex_save` latency | < 150ms | Embedding + spaCy extraction are the bottlenecks |
| `cortex_recall` (facts only) | < 10ms | SQLite index lookups |
| `cortex_recall` (full progressive) | < 50ms | Including vector search |
| `cortex_facts` latency | < 5ms | Pure graph query |
| Memory footprint | < 200MB RSS | Including loaded spaCy + sentence-transformers models |
| Storage per 1000 memories | ~5MB | Including embeddings and indexes |
| Embedding generation | < 10ms/text | Single text, CPU only |
| Token efficiency vs claude-mem | 70-90% reduction | Facts-only path vs full dump |

### Known Limitation: Cold-Start Latency

Cortex is a Python process that loads `sentence-transformers` (PyTorch) and `spaCy` — cold start is on the order of seconds, not milliseconds. This is a real cost compared to single-binary tools with no ML dependencies (e.g. Rust-based CLI proxies). It's mitigated, not eliminated, by the background daemon (`daemon.py`): the daemon keeps the embedding model resident in memory and listens on a Unix socket, so only the *first* save/recall after the daemon boots pays the cold-start cost (~5s); every request after that is ~0.3s. If the daemon isn't running (first install, or it crashed), the MCP server itself pays the full cold-start cost inline.

This is an accepted tradeoff of the current design (local NLP + local embeddings, zero API calls) rather than something actively being optimized away — there's no plan to port the hot path to a compiled language. If daemon cold-start becomes a bottleneck in practice, the next lever to pull is lazy-loading spaCy only when `claude_fallback`-style extraction actually needs it, not eagerly at daemon boot.

---

## 19. Roadmap

### Phase 1: Foundation (MVP)

- [ ] Project scaffolding (pyproject.toml, uv, src layout)
- [ ] Storage layer (sqlite3 + sqlite-vec)
- [ ] Embedding engine (sentence-transformers + all-MiniLM-L6-v2)
- [ ] Basic save/recall (embedding search, no facts yet)
- [ ] MCP server with `cortex_save` and `cortex_recall` (mcp Python SDK)
- [ ] Scope system (global + project)
- [ ] Token counting (tiktoken)

### Phase 2: Intelligence

- [ ] spaCy fact extraction (dependency parsing + NER)
- [ ] Knowledge graph storage and querying
- [ ] Progressive recall (3-layer system)
- [ ] Extractive summarization (spaCy + TF-IDF)
- [ ] Token budget system
- [ ] Deduplication (cosine similarity)
- [ ] `cortex_facts` tool

### Phase 3: Polish

- [ ] Decay score system
- [ ] `cortex_forget` with dry-run
- [ ] `cortex_scopes` management tool
- [ ] `cortex_status` diagnostics
- [ ] Full-text search (FTS5) integration
- [ ] Custom scope support
- [ ] Performance optimization & benchmarks

### Phase 4: Community

- [ ] README & documentation
- [ ] PyPI publish (`pip install cortex-claude`)
- [ ] GitHub Actions CI/CD
- [ ] Contributing guide
- [ ] Example configurations
- [ ] Benchmark suite
- [ ] Multi-language spaCy models (PT, ES, etc.)

---

## 20. Glossary

| Term | Definition |
|------|-----------|
| **Memory Unit** | Atomic piece of stored information, containing original content, summary, facts, and embedding |
| **Fact** | A subject-relation-object triplet extracted from a memory (knowledge graph node) |
| **Scope** | A named boundary for memory isolation (global, project:name, custom:name) |
| **Progressive Recall** | 3-layer retrieval strategy: facts → summaries → full chunks |
| **Decay Score** | Time-based relevance score that decreases when memories aren't accessed |
| **Token Budget** | Maximum number of tokens a recall operation should return |
| **Sufficiency** | Heuristic that determines if current retrieval layer has enough information |
| **Deduplication** | Detecting and merging near-identical memories (cosine similarity > 0.92) |
| **Extractive Summary** | Summary created by selecting the most important original sentences (no generation) |
| **spaCy** | Industrial-strength NLP library used for fact extraction (dependency parsing, NER, SVO) |
| **sqlite-vec** | SQLite extension for vector similarity search |
| **sentence-transformers** | Python library for computing text embeddings locally |

---

*This document is the single source of truth for the Cortex Claude architecture. All implementation should follow this specification. Update this document when architectural decisions change.*

### Project knowledge and execution history

Learning schema v4 adds `project_profiles`, `project_notes`, and session/revision deliveries in the same `learning.db`. Bounded, read-only manifest scanning produces declared structure; the working assistant adds sourced synthesis. Fingerprints suspend stale conclusions without erasing their evidence. Project context uses the existing automatic token budget.

Archive schema v9 transactionally moves explicitly tagged automatic tool transcripts into `execution_history`, preserving associated facts/vectors in `execution_facts` and `execution_vectors`. FTS and active vectors are removed together; affected clusters are invalidated. The migration rolls back on failure. Manual command documentation remains in normal retrieval.

## Durable recovery (0.13.0)

`reliability/queue.py` journals minimized hook events before acknowledging them. One file lock serializes replay across hook/daemon processes, receipts deduplicate completed work, and failed events block only their own session group. Database effects and the automatic checkpoint ordering cursor commit together. File-backed receipts permit replay after a process dies between the effect and acknowledgment; learning evidence and checkpoint updates are idempotent by event identity. Malformed queue files remain intact and visible while valid jobs continue.

Learning schema v5 adds automatic checkpoint metadata and durable-write timestamps. Automatic capture locks before reading the current task revision, so a manually reviewed checkpoint remains authoritative. Background project refresh and code indexing acknowledge only after their tasks finish. The daemon owns one process lock before engine initialization, drains pending jobs and performs verified backups. macOS LaunchAgents keep both daemon and localhost dashboard alive across user logins.

Backups use SQLite's online backup API, a staging directory, checksums, integrity/foreign-key checks and a publish rename. Restoration validates before publishing into a new directory. The HTTP health endpoint avoids modifying databases so failure information remains accessible even when the learning store cannot open. Codex global MCP settings share the same base as Claude; setup never modifies Codex hook-trust state.
## Reliability and project evidence in 0.14

`reliability/probe.py` exercises hook handlers in separate processes, then opens independent MCP sessions and tests a snapshot restore. Its entire memory store is disposable. Only the result metadata is persisted in the live recovery directory, so synthetic events cannot inflate real client timestamps or learning statistics.

`reliability/diagnostics.py` records bounded status transitions from the daemon worker. The web probe checks a hashed home identity, allowing it to distinguish an unavailable dashboard from one connected to another memory directory. Errors retain their categories without conversation content. Client capture/save/context stages come from actual hook processing, separately from MCP connection receipts.

`learning/analysis.py` stores additive `project_code_cache` rows in the shared database. File identity, size and nanosecond metadata allow unchanged evidence to be reused; changed content is hashed and parsed within file/byte budgets. Static call candidates remain explicitly unresolved where appropriate. `projects.py` exposes a review queue for conclusions whose source fingerprints changed. Refreshing structural evidence never revalidates those conclusions. Optional parser gaps and bounded coverage are public data, not hidden success conditions.

The package retains learning schema 5 for additive compatibility with 0.13.0. `scripts/release.py` verifies actual wheel installation across upgrade/downgrade cycles, and compares independently rebuilt wheel hashes. Evaluation records distinguish clients and normalize Codex cached input to avoid double counting. No local procedure publishes a release.
