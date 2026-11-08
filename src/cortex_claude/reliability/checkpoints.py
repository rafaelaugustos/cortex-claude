"""Automatic, explicitly partial recovery notes. No model calls or tool dumps."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.core.privacy import strip_private
from cortex_claude.learning.policy import snapshot
from cortex_claude.learning.reading import redact_lines
from cortex_claude.learning.selection import acknowledgement
from cortex_claude.learning.store import LearningStore, context_origin
from cortex_claude.reliability.config import RecoveryConfig


def compact(text: object, budget: int) -> str:
    if not isinstance(text, str):
        return ''
    text = strip_private(text)
    text = re.sub(r'(?im)^.*\b(?:password|api[_-]?key|access[_-]?token|authorization|secret)\s*[:=].*$', '[credential omitted]', text)
    text = ' '.join(redact_lines(text).split())
    if count_tokens(text) <= budget:
        return text
    words, result = text.split(), ''
    for word in words:
        candidate = (result + ' ' + word).strip()
        if count_tokens(candidate + ' …') > budget:
            break
        result = candidate
    return result + ' …' if result else ''


def capture(store: LearningStore, event: str, payload: dict, event_id: str, at: float) -> None:
    # Lock before reading the current revision: a concurrent manual save must
    # either precede this decision or follow it, never be overwritten by it.
    with store.conn:
        store.conn.execute('BEGIN IMMEDIATE')
        _capture(store, event, payload, event_id, at)


def _capture(store: LearningStore, event: str, payload: dict, event_id: str, at: float) -> None:
    if not store.config.enabled or not RecoveryConfig.load(store.home).auto_checkpoints:
        return
    sid = payload.get('session_id')
    if not sid or event not in {'UserPromptSubmit', 'PostToolUse', 'Stop', 'PreCompact', 'Interrupt', 'SessionEnd'}:
        return
    if event == 'PostToolUse' and not payload.get('changed_files'):
        return
    origin = context_origin(payload.get('cwd') or '.')
    old = store.conn.execute('SELECT * FROM automatic_checkpoints WHERE session_id=? AND origin=?', (sid, origin)).fetchone()
    if old and (old['event_at'] > at or old['event_id'] == event_id):
        return
    goal = old['goal'] if old else ''
    message = old['last_message'] if old else ''
    files = json.loads(old['files']) if old else []
    if event == 'UserPromptSubmit':
        prompt = compact(payload.get('prompt'), 55)
        if not prompt or acknowledgement(prompt):
            return
        if not re.match(r'^(?:continue|continuar|continua|retomar|retoma|resume|pick up)\b', prompt, re.I) or not goal:
            goal, message, files = prompt, '', []
    elif event == 'Stop':
        message = compact(payload.get('last_assistant_message'), 70) or message
    if not goal:
        return
    for name in payload.get('changed_files', [])[:10]:
        try:
            path = (Path(origin) / name).resolve()
            if path.is_relative_to(origin) and not any(part.startswith('.') or part in {'node_modules', 'dist', 'build', '__pycache__'} for part in path.relative_to(origin).parts):
                relative = str(path.relative_to(origin))
                files = [*filter(lambda value: value != relative, files), relative][-5:]
        except (OSError, ValueError, TypeError):
            continue
    task_id = old['task_id'] if old else 'auto:' + hashlib.sha256(f'{sid}:{origin}'.encode()).hexdigest()[:20]
    existing = store.conn.execute('SELECT * FROM work_items WHERE id=?', (task_id,)).fetchone()
    if existing and existing['state'] == 'complete':
        if event != 'UserPromptSubmit':
            return
        task_id = 'auto:' + hashlib.sha256(f'{sid}:{origin}:{event_id}'.encode()).hexdigest()[:20]
        existing = None
    # A manual revision becomes authoritative. Automatic capture never overwrites it.
    if existing and not existing['session_id'].startswith('automatic:'):
        return
    dependencies = {}
    for name in files:
        try:
            dependencies.update(snapshot(origin, [name]))
        except (OSError, ValueError):
            continue
    title = compact(goal, 18)[:120]
    summary = ('Último relato do assistente, não verificado: ' + message) if message else ('Pedido em andamento: ' + goal)
    next_step = 'Confira os arquivos e o estado atual antes de continuar.'
    pending = [compact('Arquivos recentes: ' + ', '.join(files), 28)] if files else []
    revision = existing['revision'] + 1 if existing else 1
    # One transaction binds the checkpoint and its ordering receipt. Older
    # replayed events cannot roll back a newer checkpoint.
    with store.conn:
        store.conn.execute('INSERT INTO work_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,summary=excluded.summary,pending=excluded.pending,next_step=excluded.next_step,dependencies=excluded.dependencies,revision=excluded.revision,session_id=excluded.session_id,updated_at=excluded.updated_at,expires_at=excluded.expires_at',
            (task_id, origin, title, summary, '[]', json.dumps(pending), next_step, json.dumps(dependencies), revision, 'open', 'automatic:' + sid, at, at + 14 * 86400))
        store.conn.execute('INSERT INTO automatic_checkpoints VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id,origin) DO UPDATE SET task_id=excluded.task_id,goal=excluded.goal,last_message=excluded.last_message,files=excluded.files,event_at=excluded.event_at,event_id=excluded.event_id',
            (sid, origin, payload.get('client', 'claude'), task_id, goal, message, json.dumps(files), at, event_id))


def startup_context(store: LearningStore, cwd: str, sid: str) -> dict:
    """Only a small pointer to the most recent open task; no transcript replay."""
    from cortex_claude.learning.tasks import list_tasks
    items = [item for item in list_tasks(store, cwd) if item['state'] == 'open']
    if not items:
        return {}
    latest = items[0]
    line = f"Cortex saved work: {latest['id']}: {compact(latest['title'], 20)}. "
    line += 'Sources changed; verify before resuming. ' if latest['needs_review'] else ''
    line += 'Use cortex_task resume with this task_id to inspect the saved state. Do not infer completion.'
    tokens = count_tokens(line)
    with store.conn:
        spent = store.conn.execute('SELECT injected_tokens+detail_tokens FROM sessions WHERE id=?', (sid,)).fetchone()
        if not spent or tokens > min(store.config.max_context_tokens, store.config.max_session_tokens - spent[0]):
            return {}
        if store.conn.execute('SELECT 1 FROM task_deliveries WHERE session_id=? AND task_id=? AND revision=?', (sid, latest['id'], latest['revision'])).fetchone():
            return {}
        store.conn.execute('INSERT OR REPLACE INTO task_deliveries VALUES (?,?,?)', (sid, latest['id'], latest['revision']))
        store.conn.execute('UPDATE sessions SET injected_tokens=injected_tokens+? WHERE id=?', (tokens, sid))
    return {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': line}}
