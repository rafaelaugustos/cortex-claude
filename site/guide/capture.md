---
title: Hooks and auto-capture
description: The Claude Code hooks Cortex installs - SessionStart, PreToolUse and PostToolUse - what they capture, the filter that drops noise, and the background daemon.
---

# Hooks and auto-capture

`cortex-claude setup` installs three Claude Code hooks, for every project.

## SessionStart

When a session opens, the hook tells Claude it has a memory, with a few stats and known facts, read straight from SQLite in under a second. That is what makes Claude check Cortex before saying it does not know.

It also asks the daemon to index the project into the [code graph](./code-graph) the first time you work in it.

## PreToolUse (Bash)

Before a shell command runs, the hook rewrites a short list of verbose commands into compact equivalents, so Claude reads less output:

| Claude runs | Becomes |
| --- | --- |
| `git status` | `git status --short --branch` |
| `git log` | `git log --oneline -n 20` |

Only exact, known commands are rewritten. A command with its own flags passes through untouched.

## PostToolUse

After a tool runs, its result is captured in the background: Bash, Read, Edit, Write, Grep, Glob, Agent, WebSearch, WebFetch and the tools of other MCP servers. Code files that Claude reads or edits are also indexed into the code graph.

### The capture filter

Not everything is worth remembering. Before saving, each captured result goes through a filter that looks at its size, signal words, the tool it came from and how many entities it mentions. An `ls`, a trivial read or a noisy edit is dropped. Ambiguous cases can optionally be judged by a model.

`<private>` tags work here too: see [Privacy](./privacy#private-tags).

## The daemon

A small background process keeps the embedding model loaded and listens on a local Unix socket. Saves go through it, so they take about 0.3 seconds instead of the five a cold start needs. Setup starts it; `cortex-claude daemon` runs it by hand.
