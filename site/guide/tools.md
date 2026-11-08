---
title: MCP tools
description: The fourteen MCP tools Cortex gives Claude Code - save, recall, facts, traverse, code, index_code, clusters, forget, scopes and status - with their arguments.
---

# MCP tools

Claude Code sees fourteen tools. You do not call them yourself; you ask Claude, and it picks the tool. Knowing them helps you ask well.

| Tool | Does |
| --- | --- |
| `cortex_learn` | Records, corrects, inspects or forgets shared learning |
| `cortex_read` | Bounded file reads and verified session-local diffs |
| `cortex_task` | Saves, resumes and completes compact work checkpoints |
| `cortex_save` | Saves a memory, with facts, summary and embedding |
| `cortex_recall` | Progressive recall: facts, then summaries, then full text |
| `cortex_facts` | Looks up facts about a topic in the knowledge graph |
| `cortex_traverse` | Walks the graph from an entity or a cluster |
| `cortex_code` | A symbol's definition, callers, callees and mentions |
| `cortex_index_code` | Indexes a file or folder into the code graph |
| `cortex_clusters` | Lists or rebuilds the memory clusters |
| `cortex_forget` | Deletes memories, as a dry run by default |
| `cortex_scopes` | Lists, creates, deletes, links and unlinks scopes |
| `cortex_status` | Memory and fact counts and storage per scope |

## Arguments

### cortex_learn

`content` is the conclusion (up to 80 tokens); `topic` is a stable key. `applicability` is `personal`, `transferable` or `context` (default). `triggers` contains retrieval cues. `explicit` is only for standing user instructions.

Actions: `observe`, `correct`, `experience`, `outcome`, `feedback`, `read`, `forget`, `list`, `status`. Correction, outcomes, detail reads and deletion use `lesson_id`. `conditions` accepts `all`/`any`/`none` lists. `dependencies` lists relative files; `max_age_days` sets validity.

For `experience`, provide `{situation,cause,solution}` and optionally `verification_id`; `status` lists receipts. Use `latest` only when the last successful test verifies this solution. `outcome` accepts `passed` (requires receipt) or `failed`. `read` accepts the current `query` and `max_tokens`; its details share the session budget. An explicit `session_id` avoids ambiguity between concurrent sessions. Retrieval never counts as evidence. See [Learning](./capture).

### cortex_read

Supply `path` inside the current repository, optional `start_line`/`end_line`, `max_tokens` (80–4,000; default 800), `mode` (`auto` or `full`) and optional `session_id`. Responses include a content hash, delivered range and `more`. Auto emits a diff or unchanged marker only after that session received the base; ambiguous sessions get full text. Compaction clears the cache. Use native Read directly before a native Edit that requires its own receipt; avoid duplicate inspection with both tools.

### cortex_task

Actions: `save`, `list`, `resume`, `complete`, `forget`. Saving requires `title`, `summary`, `next_step`; optional `decisions`, `pending`, `dependencies`. Keep the combined fields within 240 tokens. Updates and completion/deletion require `task_id` and `expected_revision`. Checkpoints are repository-bound in the shared database, expire after 14 days, and expose `needs_review` when tracked files change. Save at useful handoffs, not after every tool call.

Feedback uses `cortex_learn action="feedback"`, `lesson_id`, `assessment="useful"|"irrelevant"|"corrected"` and the current `query`. The assistant may assess only a lesson delivered in its session. Feedback adjusts usefulness without confirming the belief. Review conflicting preferences in the dashboard.

### cortex_save

| Argument | |
| --- | --- |
| `content` | What to remember |
| `tags` | Optional list of tags |
| `scope` | Optional; the current [scope](./scopes) otherwise |

### cortex_recall

| Argument | Default |
| --- | --- |
| `query` | |
| `depth` | `auto` (or `facts`, `summaries`, `full`) |
| `max_tokens` | `200` |
| `scope` | current |

### cortex_facts

`topic`, and optionally `relation`, `scope` and `limit` (20). Returns triplets, a few tokens each.

### cortex_traverse

`start` is an entity, or `cluster:<id>` to start from a [cluster](./clusters). `max_hops` defaults to 2.

### cortex_code and cortex_index_code

`cortex_code(symbol)` looks a symbol up. `cortex_index_code(path)` indexes a file or, with `recursive` (the default), a folder. See [The code graph](./code-graph).

### cortex_clusters

`action` is `list` (the default) or `backfill`, which rebuilds the clusters. `limit` defaults to 50.

### cortex_forget

Deletes by `query` or `memory_id`. **`dry_run` is on by default**: it shows what would go. Claude has to ask again with `dry_run=false` to delete.

### cortex_scopes

`action` is `list`, `info`, `create`, `delete`, `link` or `unlink`, with a `name` and, for linking, a `path`.

### cortex_status

Optionally for one `scope`.

## cortex_project

Project knowledge in the shared store. `refresh` reads bounded manifests and documentation headings without running commands. `read` returns modules, declared development commands and sourced conclusions (default 800 tokens, maximum 2,000). `note` records an assistant conclusion after reading 1–5 supporting files; sections are `purpose`, `architecture`, `conventions` and `decisions`. `forget_note` removes an obsolete conclusion. Source changes require review before automatic reuse. Raw execution logs are not project knowledge.
