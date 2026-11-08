"""Deterministic end-to-end evaluation; no provider calls or private user data.

Run: python scripts/evaluate_learning.py [--output /tmp/learning-evaluation.json]
Token counts use cl100k_base and describe context, not provider billing.
"""
from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.hooks import process_event
from cortex_claude.learning.extraction import Observation
from cortex_claude.learning.store import LearningStore
from cortex_claude.setup import CLAUDE_MD_CONTENT, LEGACY_CLAUDE_MD_CONTENT


def evaluate(home: Path) -> dict:
    for i, prompt in enumerate(["Prefiro funções pequenas", "I prefer small functions", "Gosto de funções pequenas"]):
        process_event("UserPromptSubmit", {"cwd": "/example/api", "session_id": f"evidence-{i}", "prompt": prompt}, home)
    with LearningStore(home) as store:
        for i in range(4):
            store.observe(Observation("The billing service uses PostgreSQL", "billing.database", "context", "billing database"), "/example/billing", f"billing-{i}")
    queries = [
        "Implement a login endpoint", "Refatore o código de autenticação",
        "Add another function", "Refactor the controller", "Implement logout",
        "Refatore as funções", "Implement refresh tokens", "Review this code",
    ]
    outputs, elapsed = [], []
    for query in queries:
        start = time.perf_counter()
        output = process_event("UserPromptSubmit", {"cwd": "/example/new-app", "session_id": "fresh-work", "prompt": query}, home)
        elapsed.append((time.perf_counter() - start) * 1000)
        outputs.append(output.get("hookSpecificOutput", {}).get("additionalContext", ""))
    irrelevant = process_event("UserPromptSubmit", {"cwd": "/example/new-app", "session_id": "vacation", "prompt": "Plan a beach vacation"}, home)
    wrong_origin = process_event("UserPromptSubmit", {"cwd": "/example/other", "session_id": "db-question", "prompt": "What database does billing use?"}, home)
    with LearningStore(home) as store:
        note = store.list()[0]
        personal = next(n for n in store.list() if n["applicability"] == "personal")
        assert personal["confirmations"] == 3
        assert note["applicability"] == "context"
        correction = store.observe(Observation("Prefer slightly larger cohesive functions", "code.function-size", "personal", "code function"), "/example/new-app", "correction", replaces=personal["id"])
        corrected = store.context("Implement code", "/example/new-app", "fresh-work")
        stats = store.stats()
    assert outputs[0] and "funções pequenas" in outputs[0]
    assert all(not output for output in outputs[1:])
    assert irrelevant == {} and wrong_origin == {}
    assert correction["status"] == "active" and "larger" in corrected["context"]
    tokens = [count_tokens(output) for output in outputs]
    # This baseline repeats the identical selected context on every turn. It
    # isolates deduplication; it is NOT a claim about whole-session API savings.
    replay_baseline = tokens[0] * len(queries)
    return {
        "scenario": "3 evidence sessions, new project, 8 relevant turns, irrelevant query, origin isolation, correction",
        "checks": {"shared_after_3_sessions": True, "same_session_not_repeated": True,
                   "irrelevant_context_empty": True, "project_fact_not_generalized": True,
                   "correction_replaces_old": True},
        "tokens_per_turn": tokens,
        "total_context_tokens": sum(tokens),
        "repeat_same_context_baseline_tokens": replay_baseline,
        "deduplication_reduction_percent": round(100 * (1 - sum(tokens) / replay_baseline), 1),
        "median_hook_logic_ms": round(statistics.median(elapsed), 2),
        "old_instruction_tokens": count_tokens(LEGACY_CLAUDE_MD_CONTENT),
        "new_instruction_tokens": count_tokens(CLAUDE_MD_CONTENT),
        "stats": stats,
        "limits": "Scripted local behavior; timings exclude process startup. Token estimates use cl100k_base, not Claude billing or total end-to-end task cost.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cortex-learning-eval-") as directory:
        result = evaluate(Path(directory))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered)
