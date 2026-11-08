---
title: Learning and automatic context
description: Shared semantic memory, verified experiences, conditions, bounded retrieval and task measurements.
---

# Learning and automatic context

Cortex keeps one shared memory with provenance. Three independent sessions consolidate a personal preference. Transferable experiences also require two origins. Contextual facts remain tied to their origin; explicit standing user instructions may apply immediately. Retrieval and repeated delivery never create evidence.

## Understanding observations

Direct EN/PT preferences are extracted locally. A resident multilingual embedding model can consolidate high-confidence paraphrases and retrieve related ideas. Negation, opposing values, numbers, technical identifiers, scope and conditions gate merging; ambiguous matches stay separate. This is a conservative heuristic, not unrestricted language understanding. Claude supplies subtler interpretations through `cortex_learn` while doing the task, without an extra model call per prompt.

Run `cortex-claude learning prepare` once to download the model. The daemon loads the cached snapshot offline. Hooks request vectors over the local socket with a 250 ms timeout; lexical matching continues if the daemon/model is unavailable. Check `learning status` for semantic readiness and indexed lessons. The default model uses roughly 470 MB on disk and additional RAM while resident.

## Verified experiences

`cortex_learn action="experience"` stores a short conclusion and an `experience` object containing `situation`, `cause`, and `solution`. Unverified episodes stay out of retrieval. To validate, provide a successful `verification_id` from `action="status"`, or `"latest"` when the latest test actually checks this solution. Receipts must belong to the current session/origin and be at most one hour old.

Recognized Bash test commands include pytest, unittest, npm/pnpm/yarn test, jest/vitest, cargo test and go test. A completed successful result with a recognized test summary is required; suppressed failures, unknown runners and help output do not qualify. Cortex never executes a remembered command. The assistant remains responsible for associating the right test with the solution: a passing test does not prove untested behavior.

After a separate application, `action="outcome"` records `passed` with a new receipt, or `failed`. Only successful independent applications confirm an experience. Failure suspends reuse until revalidated.

## Conditions and freshness

`conditions` supports `all`, `any`, and `none` lists of short task cues. For example, `{"any":["architecture","debugging"],"none":["email"]}` limits a detailed-answer preference. A matching conditional rule overrides the generic preference on the same topic. Conditions use normalized lexical cues; complex exceptions require an explicit interpretation from Claude.

`dependencies` lists up to 20 relative files to watch (maximum 2 MB each). Files must remain inside the source repository. Changed or missing files suspend the lesson. Include a dependency manifest/lockfile to track version changes. Unlisted files and versions are not inferred automatically. Experiences expire after 90 days by default; preferences may set `max_age_days`. Revalidation is explicit, and tracked files must be checked again after modification.

## Hooks

Setup preserves unrelated hooks and installs:

- **SessionStart:** registers the session, resets delivery after compaction and starts the daemon/indexing. No random context dump.
- **UserPromptSubmit:** observes direct preferences and supplies relevant compact conclusions.
- **PostToolUse:** records test receipts and indexes files; raw archival is off by default.
- **PostToolUseFailure:** records failed recognized test runs.
- **Stop:** asynchronously reads provider usage counters from the main transcript, without storing its text.

Private spans are removed before clipping. The previous command-rewriting PreToolUse hook is removed. See [Privacy](./privacy).

## Token controls

Defaults: at most 180 estimated tokens per prompt, reduced to 96 for short/weak matches, five notes and 600 tokens per session. The complete context envelope counts. Details requested with `cortex_learn action="read"` share the session budget and are delivered once. Supply the current `query` when a lesson has conditions. Compaction resets delivery receipts.

```json
{"learning":{"enabled":true,"confirmations":3,"min_contexts":2,"max_context_tokens":180,"max_session_tokens":600,"max_detail_tokens":600,"semantic_enabled":true,"semantic_timeout_ms":250,"experience_ttl_days":90,"measure_usage":true,"capture_tools":false}}
```

## Inspect and verify

The dashboard shows conclusions, evidence, conditions, test commands, stale states, estimated context and provider input/output/cache counters. Those counters cover the main session transcript, not subagents or subscription limits. Streaming/replayed message IDs are deduplicated. Legacy archives are preserved and never automatically promoted.

```bash
cortex-claude learning status
cortex-claude learning list
cortex-claude learning context "Explain architecture"
```

From a checkout:

```bash
uv run python scripts/evaluate_learning.py
uv run python scripts/evaluate_semantic.py --output /tmp/semantic.json
uv run python scripts/evaluate_tasks.py --output /tmp/tasks-offline.json
# Optional: uses your Claude account, with a budget per execution.
uv run python scripts/evaluate_tasks.py --live --repeats 2 --budget 0.40 --output /tmp/tasks.json
```

The live evaluation uses isolated synthetic projects, equal models/tools, alternating order, and an independent code grader. It records provider tokens, cache, time, failures and quality. It can report increases as well as reductions; small samples do not guarantee savings. `learning record-run run.json` imports one measured run into dashboard comparisons. Offline evaluations do not invent provider usage.

Update with `cortex-claude setup --hooks-only`, then restart Claude Code. Setup backs up changed configuration and preserves other tools' hooks.
