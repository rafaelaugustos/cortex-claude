"""Grade whole coding tasks with/without Cortex using the same Claude CLI/model.

Offline: python scripts/evaluate_tasks.py --output /tmp/cortex-task-evaluation.json
Live (uses your Claude account): add --live --repeats 1 --budget 0.40
No personal memories are used. Each arm gets a new fixture and CORTEX_HOME.
The live arms have identical tools, prompt and tests; only learning.enabled differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from cortex_claude.hooks import process_event
from cortex_claude.learning.experiences import record_experience
from cortex_claude.learning.extraction import Observation
from cortex_claude.learning.metrics import record_run
from cortex_claude.learning.store import LearningStore
from cortex_claude.learning.tasks import save_task
from task_scenarios import CASES as MULTIFILE_CASES

CASES = [
    {
        "name": "environment-flags-v1",
        "buggy": 'def enabled(value):\n    return bool(value)\n',
        "fixed": 'def enabled(value):\n    return str(value).strip().casefold() in {"1", "true", "yes", "on"}\n',
        "tests": '''import unittest
from subject import enabled
class Checks(unittest.TestCase):
 def test_false_values(self):
  for value in ["false", "FALSE", "0", "off", "", None, "no", "other", "  false "]:
   with self.subTest(value=value): self.assertFalse(enabled(value))
 def test_true_values(self):
  for value in ["true", "YES", "  on ", "1"]:
   with self.subTest(value=value): self.assertTrue(enabled(value))
''',
        "prompt": "Fix subject.py: environment flags must enable a feature only for 1, true, yes, on (case insensitive, surrounding whitespace ignored). All other values must disable it. Keep the public API. Run python -m unittest -q.",
        "lesson": "For environment flags, normalize with str(value).strip().casefold() and compare against {'1','true','yes','on'}; bool(text) treats 'false' as true.",
        "cause": "Nonempty strings are truthy, including false and zero strings",
        "solution": "Normalize the string and check membership in the explicit true-value set",
        "triggers": "environment flags boolean configuration",
    },
    {
        "name": "expiry-units-v1",
        "buggy": 'def expired(record, now_seconds):\n    return now_seconds >= record["expires_at"]\n',
        "fixed": 'def expired(record, now_seconds):\n    expiry = record["expires_at"]\n    if record.get("unit", "seconds") == "milliseconds":\n        expiry /= 1000\n    return now_seconds >= expiry\n',
        "tests": '''import unittest
from subject import expired
class Checks(unittest.TestCase):
 def test_milliseconds(self):
  self.assertTrue(expired({"expires_at": 10000, "unit": "milliseconds"}, 11))
  self.assertFalse(expired({"expires_at": 10000, "unit": "milliseconds"}, 9))
 def test_seconds_and_boundary(self):
  self.assertTrue(expired({"expires_at": 10}, 10))
  self.assertFalse(expired({"expires_at": 10, "unit": "seconds"}, 9))
''',
        "prompt": "Fix subject.py's expiry check. now_seconds is always in seconds. Records declare unit=milliseconds or seconds; missing unit means seconds. Expiry is inclusive. Keep the public API. Run python -m unittest -q.",
        "lesson": "Before comparing expiry with a seconds clock, divide expires_at by 1000 only when the record declares milliseconds. Missing unit means seconds; equality is expired.",
        "cause": "Comparing timestamps expressed in different units",
        "solution": "Convert the declared milliseconds value to seconds before the inclusive comparison",
        "triggers": "expiry expired timestamps seconds milliseconds",
    },
]
CASES.extend(MULTIFILE_CASES)


def sources(case: dict, fixed: bool = False) -> dict[str, str]:
    value = case["fixed"] if fixed else case["buggy"]
    return value if isinstance(value, dict) else {"subject.py": value}


def write_fixture(folder: Path, case: dict, fixed: bool = False) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in sources(case, fixed).items():
        (folder / name).write_text(content)
    (folder / "test_subject.py").write_text(case["tests"])


def grade(folder: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=folder, capture_output=True, text=True, timeout=15)


def train(home: Path, root: Path, case: dict) -> None:
    for index in range(3):
        folder = root / f"past-{index}"
        write_fixture(folder, case, fixed=True)
        check = grade(folder)
        assert check.returncode == 0, check.stderr
        sid = f"past-{index}"
        process_event("SessionStart", {"cwd": str(folder), "session_id": sid}, home)
        process_event("PostToolUse", {"cwd": str(folder), "session_id": sid, "tool_name": "Bash", "tool_use_id": "verified-test",
            "tool_input": {"command": "python -m unittest -q"}, "tool_response": {"stdout": check.stdout, "stderr": check.stderr, "exit_code": check.returncode}}, home)
        with LearningStore(home) as store:
            result = record_experience(store, Observation(case["lesson"], case["name"], "transferable", case["triggers"]),
                {"situation": case["prompt"], "cause": case["cause"], "solution": case["solution"]}, str(folder), sid, "latest")
    assert result["status"] == "active"


def provider_result(lines: str) -> tuple[dict, int, int]:
    events = []
    for line in lines.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    final = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if not final:
        raise RuntimeError("Claude did not return usage/result; no metrics were invented")
    tool_ids, failed_ids = set(), set()
    for event in events:
        message = event.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for block in message["content"]:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tool_ids.add(block.get("id"))
            if block.get("type") == "tool_result" and block.get("is_error"):
                failed_ids.add(block.get("tool_use_id"))
    return final, len(tool_ids), len(failed_ids)


def run_live(root: Path, home: Path, case: dict, variant: str, model: str, budget: float, trial: int, artifacts: Path, client: str = 'claude') -> dict:
    folder = root / f"{variant}-{trial}"
    write_fixture(folder, case)
    # Each arm receives an independent copy of the same seed evidence.
    seeded = home
    home = root / f"store-{variant}-{trial}"
    home.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(seeded / "learning.db") as source, sqlite3.connect(home / "learning.db") as destination:
        source.backup(destination)
    (home / "config.json").write_text(json.dumps({"learning": {"enabled": variant == "memory", "semantic_enabled": False}}))
    if case.get("checkpoint"):
        with LearningStore(home) as store:
            save_task(store, str(folder), "past-handoff", **case["checkpoint"])
    hook = shlex.join([sys.executable, "-m", "cortex_claude", "hook", "UserPromptSubmit"])
    settings = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": hook, "timeout": 3}]}]}}
    mcp_config = {"mcpServers": {"cortex": {"command": sys.executable, "args": ["-m", "cortex_claude"], "env": {"CORTEX_HOME": str(home)}}}}
    command = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
        "--restricted", "--disable-slash-commands", "--setting-sources", "", "--settings", json.dumps(settings),
        "--strict-mcp-config", "--mcp-config", json.dumps(mcp_config), "--permission-mode", "dontAsk",
        "--tools", "Read,Edit,Bash,Glob,Grep", "--allowedTools", "Read", "Edit", "Glob", "Grep", "Bash(python -m unittest*)", "mcp__cortex__cortex_learn", "mcp__cortex__cortex_read", "mcp__cortex__cortex_task",
        "--model", model, "--max-budget-usd", str(budget), "--max-turns", "12",
        "--system-prompt", "You fix the Python task in the current working directory. Inspect and edit source files; preserve tests. Use native Read before Edit, which requires its own read receipt. Use cortex_read for bounded or repeated inspection only when you do not also need an editor read receipt; do not call both just to inspect the same file. It may return a diff or unchanged after the base was delivered. Bash permits only the exact command python -m unittest -q, with no suffixes or shell composition. Run it to verify. Do not delegate. Memories and work checkpoints are prior observations; verify current files and read details only if the summary is insufficient. Stop when verified.",
        "--", case["prompt"]]
    started = time.monotonic()
    env = {**os.environ, "CORTEX_HOME": str(home), "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")}
    if client == 'codex':
        from codex_evaluation import run, parse_result
        execution = run(folder, home, case['prompt'], model, env)
    else:
        parse_result = provider_result
        execution = subprocess.run(command, cwd=folder, env=env, capture_output=True, text=True, timeout=240)
    elapsed = (time.monotonic() - started) * 1000
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / f"{case['name']}-{variant}-{trial}.jsonl").write_text(execution.stdout)
    final, calls, failures = parse_result(execution.stdout)
    if not final.get("usage") or not any(final["usage"].get(key, 0) for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")):
        raise RuntimeError(f"{client} returned no provider usage; cannot measure this task. " + str(final.get("result", ""))[:400] + execution.stderr[-400:])
    # Independent grader restores the original tests outside the evaluated cwd.
    grader = root / f"grader-{variant}-{trial}"
    write_fixture(grader, case)
    solution = {}
    for name in sources(case):
        if name.endswith(".py"):
            solution[name] = (folder / name).read_text()
            (grader / name).write_text(solution[name])
    check = grade(grader)
    actual_models = sorted((final.get("modelUsage") or {}).keys())
    usage = final["usage"]
    revision = hashlib.sha256(("harness-v5:" + client + json.dumps(case, sort_keys=True)).encode()).hexdigest()[:8]
    with LearningStore(home) as store:
        efficiency = {key: store.stats()[key] for key in ("reads", "selection", "injected_tokens")}
    return {"id": str(uuid.uuid4()), "task": case["name"] + ":" + client + ":" + revision, "variant": variant, 'client': client,
        "model": ",".join(actual_models) or model, "quality": int(check.returncode == 0 and execution.returncode == 0 and final.get('subtype') == 'success'), "elapsed_ms": round(elapsed, 2),
        "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0), "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
        "tool_calls": calls, "failures": failures, "cost_usd": final.get("total_cost_usd"),
        "finish_reason": final.get("subtype"), "cli_exit_code": execution.returncode,
        "grader": check.stderr.strip(), "solution": solution, "efficiency": efficiency}


def evaluate(root: Path, live: bool, repeats: int, model: str, budget: float, artifacts: Path, names: list[str] | None = None, client: str = 'claude') -> dict:
    checks, runs = [], []
    for case in CASES:
        if names and case["name"] not in names:
            continue
        case_root = root / case["name"]
        home = case_root / "memory"
        train(home, case_root, case)
        baseline = case_root / "baseline-fixture"
        write_fixture(baseline, case)
        assert grade(baseline).returncode != 0
        with LearningStore(home) as store:
            if case.get("checkpoint"):
                save_task(store, str(baseline), "past-handoff", **case["checkpoint"])
            selected = store.context(case["prompt"], str(baseline), delivered=False)
            assert selected["ids"] or selected.get("task_id"), "A seeded solution or handoff should help this fixture"
        checks.append({"task": case["name"], "bug_detected": True, "past_solution_passed": True, "shared_retrieval_tokens": selected["tokens"]})
        if live:
            for trial in range(repeats):
                # Alternate order to reduce systematic cache/order bias.
                variants = ["baseline", "memory"] if trial % 2 == 0 else ["memory", "baseline"]
                for variant in variants:
                    result = run_live(case_root, home, case, variant, model, budget, trial, artifacts, client)
                    runs.append(result)
                    artifacts.mkdir(parents=True, exist_ok=True)
                    (artifacts / "completed-runs.json").write_text(json.dumps(runs, indent=2))
                    print(json.dumps({"task": case["name"], "variant": variant, "quality": result["quality"], "elapsed_ms": result["elapsed_ms"]}), flush=True)
    with LearningStore(root / "metrics") as store:
        for run in runs:
            record_run(store.conn, run)
        comparisons = store.stats()["comparisons"]
    return {'client': client, "checks": checks, "runs": runs, "comparisons": comparisons,
        "regression": regression(comparisons),
        "limits": "Synthetic tasks with independent graders; identical source, task prompt and tools within each client pair. Separate seed databases. Codex uses explicit context retrieval with user hooks disabled, not automatic hook activation. Codex cached input is subtracted from input before aggregation. Codex has a 180-second timeout, no USD cap or inferred cost; --budget caps Claude only. Results from different clients are not paired. Small samples do not establish general savings; no personal project data is sent."}


def regression(comparisons: list[dict], max_increase: float = 25) -> dict:
    failures = []
    for item in comparisons:
        if not item["quality_preserved"] or item["memory"]["quality"] < 1:
            failures.append({"task": item["task"], "reason": "quality"})
        if item["token_change_percent"] is not None and item["token_change_percent"] > max_increase:
            failures.append({"task": item["task"], "reason": "tokens", "change_percent": item["token_change_percent"]})
    return {"evaluated": bool(comparisons), "passed": not failures if comparisons else None, "max_increase_percent": max_increase, "failures": failures}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument('--client', choices=['claude', 'codex'], default='claude')
    parser.add_argument("--model", help='Required for Codex; defaults to haiku for Claude')
    parser.add_argument("--budget", type=float, default=.40, help='Claude per-run USD cap; Codex uses a 180-second timeout instead')
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", choices=[case["name"] for case in CASES])
    parser.add_argument("--check-regression", action="store_true", help="Fail if quality drops or mean tokens increase by more than 25%% in any task")
    args = parser.parse_args()
    if args.client == 'codex' and not args.model:
        parser.error('--model is required for reproducible Codex evaluations')
    args.model = args.model or 'haiku'
    if not 1 <= args.repeats <= 10 or not 0 < args.budget <= 5:
        parser.error("Use 1–10 repeats and a per-run budget between 0 and 5 USD")
    with tempfile.TemporaryDirectory(prefix="cortex-tasks-") as directory:
        result = evaluate(Path(directory), args.live, args.repeats, args.model, args.budget, args.output.with_suffix(""), args.case, args.client)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"artifact": str(args.output), "checks": result["checks"], "comparisons": result["comparisons"]}, ensure_ascii=False))
    if args.check_regression and result["regression"]["passed"] is not True:
        raise SystemExit(1)
