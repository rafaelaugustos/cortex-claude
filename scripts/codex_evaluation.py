"""Codex exec adapter. Does not install, authorize, or invoke user hooks.

JSONL contract: https://learn.chatgpt.com/docs/non-interactive-mode
Cached input is a subset of Codex input_tokens; normalize before comparing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def parse_result(lines: str) -> tuple[dict, int, int]:
    usage = {'input_tokens': 0, 'output_tokens': 0, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}
    tools, failures, turns = set(), set(), 0
    completed = False
    for line in lines.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'turn.completed':
            value = event.get('usage') or {}
            total, cached, output = (value.get(k, 0) for k in ('input_tokens', 'cached_input_tokens', 'output_tokens'))
            if any(type(n) is not int or n < 0 for n in (total, cached, output)) or cached > total:
                raise ValueError('Invalid Codex usage counters')
            usage['input_tokens'] += total - cached
            usage['cache_read_input_tokens'] += cached
            usage['output_tokens'] += output
            turns += 1
            completed = True
        elif event.get('type') in {'turn.failed', 'error'}:
            completed = False
        elif event.get('type') == 'item.completed':
            item = event.get('item') or {}
            if item.get('type') in {'command_execution', 'mcp_tool_call', 'file_change'}:
                tools.add(item.get('id'))
                if item.get('status') == 'failed' or item.get('exit_code', 0) not in (0, None):
                    failures.add(item.get('id'))
    if not turns or not sum(usage.values()):
        raise RuntimeError('Codex returned no completed turn with provider usage; no metrics were invented')
    return {'usage': usage, 'subtype': 'success' if completed else 'failed', 'total_cost_usd': None}, len(tools), len(failures)


def run(folder: Path, home: Path, prompt: str, model: str, env: dict, *, timeout: int = 180):
    from cortex_claude.hooks import process_event
    # Explicit retrieval in this runner keeps the user's deferred hook trust intact.
    selected = process_event('UserPromptSubmit', {'cwd': str(folder), 'session_id': 'codex:evaluation', 'prompt': prompt}, home)
    context = selected.get('hookSpecificOutput', {}).get('additionalContext', '')
    mcp = {'command': sys.executable, 'args': ['-m', 'cortex_claude'],
           'env': {'CORTEX_HOME': str(home), 'CORTEX_CLIENT': 'codex'}, 'startup_timeout_sec': 30}
    # TOML inline table, not JSON: all string values are explicitly encoded.
    from cortex_claude.reliability.clients import _toml
    command = ['codex', 'exec', '--json', '--ephemeral', '--ignore-user-config', '--skip-git-repo-check',
        '--sandbox', 'workspace-write', '--disable', 'hooks', '--disable', 'apps', '--disable', 'multi_agent',
        '-c', 'approval_policy="never"', '-c', 'mcp_servers.cortex=' + _toml(mcp),
        '-c', 'model_reasoning_effort="low"', '-c', 'shell_environment_policy.inherit="all"',
        '--add-dir', str(home), '--cd', str(folder), '--model', model]
    instruction = ('Fix the Python task in this directory. Inspect and edit source files; preserve tests. '
        'Run python -m unittest -q to verify. Do not delegate or access external services. '
        'Only use Cortex for relevant missing context; verify memories against current files. '
        'Finish after the tests pass.\n\n' + prompt + ('\n\n' + context if context else ''))
    return subprocess.run([*command, '--', instruction], cwd=folder,
        env={**env, 'CORTEX_CLIENT': 'codex'}, capture_output=True, text=True, timeout=timeout)
