---
title: Privacy
description: Cortex is local first. SQLite, local embeddings and local NLP, private tags to keep secrets out of memory, the optional Claude extraction, and a dashboard locked to localhost.
---

# Privacy

Cortex runs on your machine. Memories, facts, embeddings and the code graph are in SQLite under `~/.cortex-claude`. Embeddings and fact extraction run locally. There is no account, no service and no telemetry.

The network is used to download the embedding and spaCy models during setup, and not otherwise, unless you turn on Claude-assisted extraction.

## Private tags

Wrap anything you do not want remembered in `<private>` tags:

```text
The API uses JWT for auth. <private>API_KEY=sk-abc123secret</private> Tokens expire in 24h.
```

Cortex removes everything between the tags before saving, in saves you ask for and in [auto-capture](./capture). If everything is private, nothing is saved.

## Claude-assisted extraction

Off by default. With the `claude` extra installed, `claude_fallback: true` in the [configuration](./configuration#facts) and an `ANTHROPIC_API_KEY` in the environment, Cortex sends the text of a memory to Claude Haiku when local extraction finds fewer than two confident facts. That text then goes to Anthropic, through your API key, and is billed to it.

## Memory that Claude reads

What Cortex returns goes into Claude Code's context, and from there to the model like everything else in the session. Keeping recall small is also keeping that small.

## The dashboard

The [dashboard](./dashboard) listens on localhost only and checks the `Host` and `Origin` of every request, so other pages in your browser cannot read or change your memory.

## Forgetting

Ask Claude to forget something; it shows what would be deleted first (`cortex_forget` runs as a dry run by default). For bulk cleanup with a preview, use the dashboard.
