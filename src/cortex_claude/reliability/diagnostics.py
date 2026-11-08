"""Bounded local incident history, containing health metadata only."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.request import urlopen

from cortex_claude.reliability.config import RecoveryConfig
from cortex_claude.reliability.files import lock, read_json, write_json


def identity(home: Path) -> str:
    return hashlib.sha256(str(home.resolve()).encode()).hexdigest()[:16]


def history(home: Path) -> dict:
    try:
        return read_json(home / 'recovery' / 'diagnostics.json')
    except (OSError, ValueError):
        return {'unreadable': True}


def sample(home: Path) -> dict:
    from cortex_claude.reliability.health import report
    now = time.time()
    codes = []
    try:
        health = report(home)
        if not health['daemon']['running']:
            codes.append('daemon_unavailable')
        if any(not db['readable'] for db in health['databases']):
            codes.append('database_unreadable')
        if health['queue']['failures']:
            codes.append('queue_failed')
        if health['queue']['oldest_at'] and now - health['queue']['oldest_at'] > 60:
            codes.append('queue_delayed')
        if health['policy']['auto_backup'] and (not health['backups'] or now - health['backups'][0]['created_at'] > health['policy']['interval_hours'] * 7200):
            codes.append('backup_overdue')
        if health['heartbeat_at'] and now - health['heartbeat_at'] > 300:
            codes.append('worker_stalled')
        for client, value in health['clients'].items():
            received = value.get('last_received_at')
            if received and received > (value.get('last_saved_at') or 0) and now - received > 60:
                codes.append(client + '_capture_delayed')
        if health.get('issues') and not codes:
            codes.append('health_attention')
        port = RecoveryConfig.load(home).web_port
        try:
            with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=2) as response:
                web = json.loads(response.read(200_000))
            if not web.get('instance'):
                codes.append('web_version_mismatch')
            elif web['instance'] != identity(home):
                codes.append('web_wrong_instance')
            elif any(not db['readable'] for db in web['databases']) or not web['daemon']['running']:
                codes.append('web_access_failure')
        except (OSError, ValueError, KeyError, TypeError):
            codes.append('web_unavailable')
    except Exception as error:
        codes.append('diagnostic_failed:' + type(error).__name__)
    codes = sorted(set(codes))
    with lock(home / 'recovery' / 'diagnostics.lock'):
        previous = history(home)
        events = previous.get('events', [])
        if previous.get('codes') != codes:
            events.append({'at': now, 'status': 'attention' if codes else 'healthy', 'codes': codes})
        result = {'checked_at': now, 'status': 'attention' if codes else 'healthy', 'codes': codes, 'events': events[-100:]}
        write_json(home / 'recovery' / 'diagnostics.json', result)
    return result
