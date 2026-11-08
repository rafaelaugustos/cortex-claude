from __future__ import annotations

import json
import shutil
import socket
import sqlite3
import time
import tomllib
from contextlib import closing
from pathlib import Path

from cortex_claude import __version__
from cortex_claude.reliability.backups import snapshots
from cortex_claude.reliability.config import RecoveryConfig
from cortex_claude.reliability.files import read_json
from cortex_claude.reliability.queue import pending
from cortex_claude.reliability.services import status as service_status
from cortex_claude.reliability.diagnostics import history, identity


def ping(home: Path) -> dict:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(.25)
            stream.connect(str(home / 'cortex.sock'))
            stream.sendall(b'{"action":"ping"}')
            stream.shutdown(socket.SHUT_WR)
            value = json.loads(stream.recv(4096))
            return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def report(home: Path) -> dict:
    issues, databases = [], []
    saved_at = 0
    try:
        config = RecoveryConfig.load(home)
    except (OSError, ValueError, TypeError):
        config = RecoveryConfig()
        issues.append('A configuração do Cortex precisa ser corrigida.')
    try:
        current = read_json(home / 'recovery' / 'state.json')
    except (ValueError, OSError):
        current = {}
        issues.append('O registro de recuperação não pôde ser lido.')
    jobs = pending(home)
    failures = [job for job in jobs if job['error']]
    daemon = ping(home)
    if daemon.get('status') != 'running':
        issues.append('O serviço de memória está indisponível.')
    if current.get('service_error'):
        issues.append('O processamento em segundo plano encontrou uma falha e tentará novamente.')
    elif daemon.get('status') == 'running' and current.get('heartbeat_at') and time.time() - current['heartbeat_at'] > 300:
        issues.append('O processamento em segundo plano não confirmou atividade recente.')
    paths = [home / 'learning.db', home / 'global.db', *sorted((home / 'scopes').glob('*.db'))]
    for path in paths:
        if not path.exists():
            if path.name == 'learning.db':
                issues.append('A base compartilhada ainda não foi criada.')
            continue
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.25)) as conn:
                conn.execute('SELECT name FROM sqlite_master LIMIT 1').fetchone()
                if path.name == 'learning.db':
                    row = conn.execute('SELECT saved_at FROM durable_writes WHERE id=1').fetchone()
                    saved_at = row[0] if row else 0
            databases.append({'name': str(path.relative_to(home)), 'readable': True})
        except sqlite3.Error:
            databases.append({'name': str(path.relative_to(home)), 'readable': False})
            issues.append(f'Não foi possível abrir {path.name}. Os dados não foram substituídos.')
    backups = snapshots(home)
    if config.auto_backup and (not backups or time.time() - backups[0]['created_at'] > config.backup_interval_hours * 7200):
        issues.append('Ainda não há um backup automático recente e verificado.')
    if failures:
        issues.append(f'{len(failures)} operações aguardam nova tentativa após falhas.')
    if current.get('backup_error'):
        issues.append('A última tentativa de backup falhou. As cópias anteriores foram preservadas.')
    disk = shutil.disk_usage(home if home.exists() else home.parent)
    if disk.free < 100 * 1024 * 1024:
        issues.append('Pouco espaço em disco para salvar memória e criar backups.')
    clients = {}
    for client, path in [('claude', Path.home() / '.claude.json'), ('codex', Path.home() / '.codex/config.toml')]:
        configured = False
        try:
            value = tomllib.loads(path.read_text()) if client == 'codex' else json.loads(path.read_text())
            configured = 'cortex' in value.get('mcp_servers' if client == 'codex' else 'mcpServers', {})
        except (OSError, ValueError):
            pass
        clients[client] = {'configured': configured, 'last_hook_at': current.get(f'client_{client}_at'), 'last_mcp_at': current.get(f'mcp_{client}_at'),
                           'last_received_at': current.get(f'client_{client}_received_at'), 'last_saved_at': current.get(f'client_{client}_saved_at'), 'last_context_at': current.get(f'client_{client}_context_at')}
    error_file = home / 'hook-error.log'
    if error_file.exists() and error_file.stat().st_mtime > current.get('last_applied_at', 0):
        issues.append('Um hook não conseguiu confirmar o salvamento. Confira a integração do cliente.')
    try:
        probe = read_json(home / 'recovery' / 'probe.json')
    except (OSError, ValueError):
        probe = {'status': 'unreadable'}
    return {'version': __version__, 'instance': identity(home), 'status': 'attention' if issues else 'healthy', 'issues': issues,
            'diagnostics': history(home), 'self_test': probe,
            'daemon': {'running': daemon.get('status') == 'running', 'semantic': daemon.get('semantic', 'unavailable')},
            'last_saved_at': saved_at, 'last_processed_at': current.get('last_applied_at'), 'heartbeat_at': current.get('heartbeat_at'),
            'queue': {'pending': len(jobs), 'failures': len(failures), 'oldest_at': jobs[0]['created_at'] if jobs else None,
                      'items': [{key: job[key] for key in ('id', 'kind', 'attempts', 'error', 'created_at', 'next_attempt')} for job in jobs[:25]]},
            'backups': backups, 'last_restore_test_at': current.get('last_restore_test_at'),
            'policy': {'auto_backup': config.auto_backup, 'interval_hours': config.backup_interval_hours, 'keep': config.backup_keep,
                       'mirror_configured': bool(config.mirror_directory), 'auto_checkpoints': config.auto_checkpoints},
            'disk_free_bytes': disk.free, 'databases': databases, 'clients': clients, 'services': service_status()}
