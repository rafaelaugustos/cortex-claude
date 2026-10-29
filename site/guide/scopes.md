---
title: Scopes
description: Cortex scopes keep memory global, per project or in your own boundaries. Link folders to scopes, set the search order, and manage them with cortex_scopes.
---

# Scopes

A **scope** is a separate memory. By default there is one, `global`, shared by every project.

## Project scopes

Link a folder to its own scope and what you save while working there stays there:

```json
{
  "scopes": {
    "mappings": {
      "/Users/me/work/shop": "project:shop",
      "/Users/me/work/api": "project:api"
    },
    "default": "global",
    "search_order": "project_first"
  }
}
```

With `project_first`, recall looks in the project's scope before the global one, so project details win and general knowledge still comes through.

The [code graph](./code-graph) of a project without a mapping goes to an automatic `project:<folder-name>` scope, so code never fills the global memory.

## Managing scopes

Ask Claude, which uses `cortex_scopes`:

| Action | Does |
| --- | --- |
| `list` | All scopes |
| `info` | Details of one |
| `create` | A new scope |
| `delete` | Removes a scope and its memory |
| `link` | Links a folder to a scope |
| `unlink` | Removes a folder's link |

`cortex_status` shows memory and fact counts and storage for each scope.
