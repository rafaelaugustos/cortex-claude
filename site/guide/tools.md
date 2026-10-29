---
title: MCP tools
description: The ten MCP tools Cortex gives Claude Code - save, recall, facts, traverse, code, index_code, clusters, forget, scopes and status - with their arguments.
---

# MCP tools

Claude Code sees ten tools. You do not call them yourself; you ask Claude, and it picks the tool. Knowing them helps you ask well.

| Tool | Does |
| --- | --- |
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
