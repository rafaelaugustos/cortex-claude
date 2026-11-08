"""A disk-backed inbox. Acknowledgment follows durable effects, never precedes them.

Replays can happen after a crash between effect and receipt. Handlers must be
idempotent. Completed receipts contain no prompts, commands or tool output.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from pathlib import Path
from typing import Callable

from cortex_claude.reliability.files import lock, read_json, state, write_json


def enqueue(home: Path, kind: str, payload: dict, identity: str | None = None) -> str:
    job_id = hashlib.sha256((identity or uuid.uuid4().hex).encode()).hexdigest()
    root = home / 'recovery'
    with lock(root / 'inbox.lock'):
        if (root / 'receipts' / f'{job_id}.json').exists() or (root / 'pending' / f'{job_id}.json').exists():
            return job_id
        write_json(root / 'pending' / f'{job_id}.json', {
            'id': job_id, 'kind': kind, 'payload': payload, 'created_at': time.time(),
            'attempts': 0, 'next_attempt': 0, 'error': None,
        })
    state(home, last_queued_at=time.time())
    return job_id


def pending(home: Path) -> list[dict]:
    items = []
    for path in (home / 'recovery' / 'pending').glob('*.json'):
        try:
            job = read_json(path)
            if (job.get('id') != path.stem or not isinstance(job.get('payload'), dict)
                    or not isinstance(job.get('kind'), str)
                    or not all(isinstance(job.get(key), (int, float)) and math.isfinite(job[key]) and job[key] >= 0 for key in ('created_at', 'attempts', 'next_attempt'))
                    or not isinstance(job['attempts'], int) or 'error' not in job):
                raise ValueError('Invalid pending job')
            data = job['payload'].get('data', job['payload'])
            if not isinstance(data, dict) or not isinstance(data.get('session_id', data.get('cwd', '')), str):
                raise ValueError('Invalid pending payload')
            items.append(job)
        except (ValueError, OSError):
            try:
                modified = path.stat().st_mtime
            except FileNotFoundError:
                continue
            items.append({'id': path.stem, 'kind': 'invalid', 'created_at': modified, 'attempts': 0, 'next_attempt': 0, 'error': 'InvalidJob', 'payload': {}})
    return sorted(items, key=lambda item: (item['created_at'], item['id']))


def drain(home: Path, handler: Callable[[dict], None], *, limit: int = 20,
          seconds: float = 2, kinds: set[str] | None = None) -> dict:
    count, errors, started = 0, 0, time.monotonic()
    try:
        with lock(home / 'recovery' / 'worker.lock', blocking=False):
            blocked = set()
            for job in pending(home):
                if count + errors >= limit or time.monotonic() - started >= seconds:
                    break
                if kinds is not None and job['kind'] not in kinds:
                    continue
                if job['kind'] == 'invalid':
                    # Keep the original bytes for diagnosis and recovery.
                    # A malformed record must not stop other valid jobs.
                    errors += 1
                    continue
                data = job['payload'].get('data', job['payload'])
                group = (job['kind'], data.get('session_id', data.get('cwd', '')))
                if group in blocked:
                    continue
                if job['next_attempt'] > time.time():
                    blocked.add(group)
                    continue
                path = home / 'recovery' / 'pending' / f"{job['id']}.json"
                receipt = home / 'recovery' / 'receipts' / f"{job['id']}.json"
                if receipt.exists():
                    path.unlink(missing_ok=True)
                    continue
                try:
                    if job['kind'] == 'invalid':
                        raise ValueError('Invalid pending job')
                    handler(job)
                    write_json(receipt, {'id': job['id'], 'completed_at': time.time()})
                    path.unlink(missing_ok=True)
                    state(home, last_applied_at=time.time())
                    count += 1
                except Exception as error:
                    blocked.add(group)
                    job['attempts'] += 1
                    job['next_attempt'] = time.time() + min(300, 2 ** min(job['attempts'], 9))
                    job['error'] = type(error).__name__
                    write_json(path, job)
                    state(home, last_error={'kind': job['kind'], 'type': type(error).__name__, 'at': time.time()})
                    errors += 1
    except BlockingIOError:
        return {'processed': 0, 'errors': 0, 'busy': True}
    return {'processed': count, 'errors': errors, 'busy': False}


def retry(home: Path) -> dict:
    count = 0
    with lock(home / 'recovery' / 'worker.lock'):
        for job in pending(home):
            if job['kind'] == 'invalid':
                continue
            job['next_attempt'] = 0
            write_json(home / 'recovery' / 'pending' / f"{job['id']}.json", job)
            count += 1
    return {'scheduled': count}


def prune_receipts(home: Path) -> None:
    cutoff = time.time() - 30 * 86400
    for path in (home / 'recovery' / 'receipts').glob('*.json'):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
