---
title: What is Cortex?
description: Cortex is an open-source, local MCP memory server for Claude Code, with progressive recall, a knowledge graph, a code graph and automatic capture through hooks.
---

# What is Cortex?

Cortex gives [Claude Code](https://claude.ai/claude-code) a memory that lasts across sessions. It runs on your machine as an MCP server, stores everything in SQLite, and is open source under the MIT license.

Most memory tools inject a pile of notes into every prompt. Cortex does the opposite: Claude asks, and Cortex answers with the least it can.

## The idea

When something is saved, Cortex keeps it three ways:

<ul class="layers">
  <li><strong>Facts</strong><span>Subject, relation, object triplets. A few tokens each.</span></li>
  <li><strong>Summary</strong><span>About a quarter of the original.</span></li>
  <li><strong>Full text</strong><span>The original, only when the others are not enough.</span></li>
</ul>

Recall starts with facts and stops at the first layer that answers the question. See [How recall works](./how-it-works).

## What else it does

- **[Knowledge graph](./knowledge-graph):** facts link entities together, and Claude can walk the connections.
- **[Code graph](./code-graph):** the symbols of your codebase in the same graph, so "who calls this?" costs about a hundred tokens instead of reading files.
- **[Clusters](./clusters):** memories group themselves by meaning.
- **[Hooks](./capture):** Claude Code's tool results are captured, filtered and saved without you asking.
- **[Scopes](./scopes):** global memory, per-project memory, or your own boundaries.
- **[Dashboard](./dashboard):** a local web view of your memory.

## Using it

After [installing](./install), talk to Claude as usual:

```text
Remember that the API rate limit is 500 requests per minute.
What do you know about rate limiting?
What's connected to the auth service?
Forget what I said about the old API key.
```

Claude decides when to use the [Cortex tools](./tools). Setup also adds instructions to your `~/.claude/CLAUDE.md` so it checks memory before saying it does not know.
