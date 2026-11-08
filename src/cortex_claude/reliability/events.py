from __future__ import annotations

import json
import re
from pathlib import Path

from cortex_claude.core.privacy import strip_private
from cortex_claude.reliability.checkpoints import compact
from cortex_claude.reliability.queue import enqueue


def normalize(event: str, payload: dict, client: str) -> dict:
    if client not in {'claude', 'codex'}:
        raise ValueError('Unknown memory client')
    sid = payload.get('session_id') or payload.get('thread-id')
    result: dict = {'client': client, 'cwd': str(Path(payload.get('cwd') or '.').resolve())}
    if isinstance(sid, str):
        result['session_id'] = sid if sid.startswith(client + ':') else client + ':' + sid
    for key in ('source', 'turn_id', 'tool_use_id', 'transcript_path'):
        if isinstance(payload.get(key), str):
            result[key] = strip_private(payload[key])[:4096]
    if event == 'UserPromptSubmit':
        result['prompt'] = compact(payload.get('prompt'), 2000)
    if event == 'Stop':
        result['last_assistant_message'] = compact(payload.get('last_assistant_message'), 160)
    if event in {'PostToolUse', 'PostToolUseFailure'}:
        name = payload.get('tool_name', '')
        result['tool_name'] = name
        inputs = payload.get('tool_input') or {}
        if not isinstance(inputs, dict):
            inputs = {}
        result['tool_input'] = {}
        if name in {'Read', 'Edit', 'Write'} and isinstance(inputs.get('file_path'), str):
            result['tool_input'] = {'file_path': inputs['file_path']}
            if name != 'Read':
                result['changed_files'] = [inputs['file_path']]
        if name == 'apply_patch':
            patch = inputs.get('command') or inputs.get('patch') or ''
            result['changed_files'] = re.findall(r'^\*\*\* (?:Add|Update|Delete) File: (.+)$', patch, re.M)[:10] if isinstance(patch, str) else []
        if name == 'Bash':
            command = inputs.get('command') or inputs.get('cmd') or ''
            result['tool_input'] = {'command': compact(command, 300)}
            response = payload.get('tool_response')
            text = strip_private(response if isinstance(response, str) else '\n'.join(str(response.get(key, '')) for key in ('stdout', 'stderr', 'output')) if isinstance(response, dict) else '')
            # Keep only test-result markers, never stdout or the shell transcript.
            markers = re.findall(r'\b\d+\s+(?:passed|failed|errors?|passing|failing)\b|\b(?:PASS|FAIL|OK)\b', text, re.I)
            response_dict = response if isinstance(response, dict) else {}
            code = response_dict.get('exit_code', response_dict.get('exitCode'))
            if code is None:
                match = re.search(r'(?:exit(?:ed)? (?:with )?code|Process exited with code)\s*[:=]?\s*(\d+)', text, re.I)
                code = int(match[1]) if match else None
            if code is None and client == 'claude' and event == 'PostToolUse' and not response_dict.get('interrupted'):
                code = 0
            result['tool_response'] = {'stdout': ' '.join(markers[:30]), 'exit_code': code, 'interrupted': bool(response_dict.get('interrupted'))}
        elif name not in {'Read', 'Edit', 'Write', 'apply_patch', 'Grep', 'Glob', 'ToolSearch', 'TaskCreate', 'TaskUpdate', 'TaskList', 'StructuredOutput'} and 'cortex' not in name.lower():
            # The opt-in legacy filter may still use short non-execution text.
            response = payload.get('tool_response', '')
            result['tool_response'] = compact(response if isinstance(response, str) else json.dumps(response), 350)
    if 'changed_files' in result:
        result['changed_files'] = [str((Path(result['cwd']) / name).resolve()) for name in result['changed_files']]
    return result


def apply(home: Path, job: dict) -> None:
    from cortex_claude.hooks import process_event
    from cortex_claude.learning.store import LearningStore
    from cortex_claude.reliability.checkpoints import capture
    event, payload = job['payload']['event'], {**job['payload']['data'], '_event_id': job['id']}
    process_event(event, payload, home, retrieve=False)
    with LearningStore(home) as store:
        capture(store, event, payload, job['id'], job['created_at'])
    from cortex_claude.reliability.files import state
    import time
    client = payload.get('client', 'claude')
    state(home, **{f"client_{client}_at": job['created_at'], f'client_{client}_saved_at': time.time()})
    if event == 'SessionStart':
        enqueue(home, 'daemon', {'action': 'index_project', 'cwd': payload['cwd']}, 'project-start:' + job['id'])


def queue_work(home: Path, payload: dict, identity: str | None = None) -> None:
    enqueue(home, 'daemon', payload, identity + ':' + json.dumps(payload, sort_keys=True) if identity else None)
