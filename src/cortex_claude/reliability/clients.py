"""Install the shared memory client without replacing unrelated user settings."""
from __future__ import annotations

import copy
import json
import re
import shlex
import sys
import time
import tomllib
from pathlib import Path

from cortex_claude.reliability.files import atomic_write, read_json, write_json

_START, _END = '<!-- cortex-recovery:start -->', '<!-- cortex-recovery:end -->'
INSTRUCTIONS = '''Use Cortex as shared, local project memory. At the start of repository work, read cortex_project (refresh if absent/stale) and list cortex_task checkpoints. Automatic checkpoints are partial, unverified recovery notes; inspect current files before continuing. Never infer completed work from a saved note.
After understanding source files, save concise architecture/conventions/decisions with cortex_project note and source paths. Save a structured cortex_task checkpoint at meaningful milestones, with objective, decisions, pending work, next step and file dependencies; use expected_revision for updates. Complete finished tasks. This complements automatic recovery without saving tool transcripts.
Use cortex_learn for durable preferences and verified reusable lessons. Current user instructions and current source code take precedence. Reads never count as confirmations. Consult cortex_recall only for missing context; avoid repeated full reads. A failed memory tool call is not a successful save: report it, and do not promise persistence until confirmed. Never save raw commands or stdout as knowledge.
'''


def _toml(value) -> str:
    if isinstance(value, dict):
        return '{' + ', '.join(json.dumps(str(key)) + ' = ' + _toml(item) for key, item in value.items()) + '}'
    if isinstance(value, list):
        return '[' + ', '.join(_toml(item) for item in value) + ']'
    if isinstance(value, (str, bool, int, float)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    raise ValueError('Unsupported TOML setting; existing config left unchanged')


def configure_toml(original: str, command: str, home: Path) -> str:
    before = tomllib.loads(original)
    previous = before.get('mcp_servers', {}).get('cortex', {})
    entry = {**previous, 'command': command, 'args': ['-m', 'cortex_claude'], 'enabled': True,
             'env': {**previous.get('env', {}), 'CORTEX_HOME': str(home), 'CORTEX_CLIENT': 'codex'},
             'startup_timeout_sec': 30}
    # Remove only this server's tables, then prove all other parsed data stays
    # identical. Unusual inline/multiline layouts fail safely before any write.
    headers = list(re.finditer(r'(?m)^\s*(\[\[?[^\n]+?\]\]?)\s*(?:#[^\n]*)?$', original))
    remove = []
    for index, match in enumerate(headers):
        header = match[1].strip('[]').replace('"', '').replace("'", '').replace(' ', '')
        if header == 'mcp_servers.cortex' or header.startswith('mcp_servers.cortex.'):
            remove.append((match.start(), headers[index + 1].start() if index + 1 < len(headers) else len(original)))
    result = original
    for start, stop in reversed(remove):
        result = result[:start] + result[stop:]
    result = result.rstrip() + '\n\n[mcp_servers.cortex]\n' + ''.join(key + ' = ' + _toml(value) + '\n' for key, value in entry.items())
    after = tomllib.loads(result)
    expected = copy.deepcopy(before)
    expected.setdefault('mcp_servers', {})['cortex'] = entry
    if after != expected:
        raise ValueError('Cannot update Cortex without modifying unrelated Codex configuration')
    return result


def _backup(path: Path) -> None:
    if path.exists():
        atomic_write(path.with_name(path.name + f'.cortex-backup-{time.time_ns()}'), path.read_bytes())


def install_codex(home: Path, codex_directory: Path, python: str | None = None) -> dict:
    python = python or sys.executable
    home, codex_directory = home.resolve(), codex_directory.expanduser()
    config_path = codex_directory / 'config.toml'
    original = config_path.read_text() if config_path.exists() else ''
    updated = configure_toml(original, python, home)
    hooks_path = codex_directory / 'hooks.json'
    hook_config = read_json(hooks_path)
    hooks = hook_config.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Invalid Codex hooks; existing configuration left untouched')
    events = ('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop', 'PreCompact', 'Interrupt', 'SessionEnd')
    scripts = {event: home / 'hooks' / f'codex-{event}.sh' for event in events}
    owned = {shlex.quote(str(path)) for path in scripts.values()}
    for event, groups in list(hooks.items()):
        preserved = []
        for group in groups:
            remaining = [hook for hook in group.get('hooks', []) if hook.get('command') not in owned]
            if remaining:
                preserved.append({**group, 'hooks': remaining})
        hooks[event] = preserved
    for event, path in scripts.items():
        body = '#!/bin/sh\nexport CORTEX_HOME=' + shlex.quote(str(home)) + '\nexec ' + shlex.quote(python) + ' -m cortex_claude hook ' + event + ' codex\n'
        atomic_write(path, body.encode())
        path.chmod(0o700)
        hooks.setdefault(event, []).append({'hooks': [{'type': 'command', 'command': shlex.quote(str(path)), 'timeout': 3 if event in {'Interrupt', 'SessionEnd'} else 5}]})
    instructions_path = codex_directory / 'AGENTS.md'
    instructions = instructions_path.read_text() if instructions_path.exists() else ''
    block = _START + '\n' + INSTRUCTIONS + _END
    if _START in instructions:
        if instructions.count(_START) != 1 or instructions.count(_END) != 1:
            raise ValueError('Ambiguous Cortex instruction markers; user instructions left untouched')
        start, end = instructions.index(_START), instructions.index(_END) + len(_END)
        instructions_new = instructions[:start] + block + instructions[end:]
    else:
        instructions_new = instructions.rstrip() + '\n\n' + block + '\n'
    for path, contents in [(config_path, updated), (hooks_path, json.dumps(hook_config, indent=2, ensure_ascii=False) + '\n'), (instructions_path, instructions_new)]:
        if not path.exists() or path.read_text() != contents:
            _backup(path)
            atomic_write(path, contents.encode())
    return {'configured': True, 'config': str(config_path), 'hooks': str(hooks_path), 'review_required': True,
            'next': 'Restart Codex and review the Cortex hooks in /hooks. Hook trust is never bypassed by setup.'}
