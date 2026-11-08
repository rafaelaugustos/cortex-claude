"""A bounded, isolated round trip through real hooks, MCP and backup APIs."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from cortex_claude.reliability.files import lock, write_json


async def _mcp(home: Path, repo: Path, client: str, name: str, arguments: dict):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=['-m', 'cortex_claude'],
        cwd=str(repo), env={**os.environ, 'CORTEX_HOME': str(home), 'CORTEX_CLIENT': client})
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
        await session.initialize()
        result = await session.call_tool(name, arguments)
        if result.isError:
            raise ValueError('MCP returned an error')
        value = json.loads(result.content[0].text)
        if isinstance(value, dict) and value.get('error'):
            raise ValueError('MCP rejected the operation')
        return value


def run(home: Path) -> dict:
    """Never modify live lessons or claim that client-side hooks are enabled."""
    started = time.time()
    result = {'status': 'failed', 'started_at': started, 'checks': [],
              'scope': 'isolated-processes', 'client_activation_tested': False}
    root = home / 'recovery'
    root.mkdir(parents=True, exist_ok=True)
    with lock(root / 'probe.lock', blocking=False):
        try:
            with tempfile.TemporaryDirectory(prefix='probe-', dir=root) as directory:
                base = Path(directory).resolve()
                memory, repo = base / 'memory', base / 'repo'
                memory.mkdir(); repo.mkdir()
                (repo / 'package.json').write_text('{"name":"cortex-recovery-probe"}')
                (memory / 'config.json').write_text(json.dumps({'learning': {'semantic_enabled': False},
                    'clustering': {'enabled': False}, 'reliability': {'auto_backup': False}}))
                env = {**os.environ, 'CORTEX_HOME': str(memory)}

                def hook(client, sid, prompt):
                    execution = subprocess.run([sys.executable, '-m', 'cortex_claude', 'hook', 'UserPromptSubmit', client],
                        input=json.dumps({'session_id': sid, 'cwd': str(repo), 'prompt': prompt}),
                        env=env, capture_output=True, text=True, timeout=20)
                    if execution.returncode or (memory / 'hook-error.log').exists():
                        raise RuntimeError('Hook round trip failed')
                    return json.loads(execution.stdout or '{}')

                def passed(name):
                    result['checks'].append({'name': name, 'passed': True})

                for writer, reader in [('claude', 'codex'), ('codex', 'claude')]:
                    hook(writer, writer + '-teach', 'Sempre prefiro usar pytest para testes Python')
                    from cortex_claude.learning.store import LearningStore
                    from cortex_claude.reliability.queue import pending
                    with LearningStore(memory) as store:
                        if not store.conn.execute("SELECT 1 FROM lessons WHERE state='active'").fetchone() or pending(memory):
                            raise RuntimeError('Capture was not durably acknowledged')
                    passed(writer + ':capture-and-save')
                    recovered = hook(reader, writer + '-new-session', 'Como organizar testes Python usando pytest?')
                    if 'pytest' not in recovered.get('hookSpecificOutput', {}).get('additionalContext', '').lower():
                        raise RuntimeError('New process did not recall the saved preference')
                    passed(writer + '-to-' + reader + ':new-session-recall')
                    repeated = hook(reader, writer + '-new-session', 'Como organizar testes Python usando pytest?')
                    if repeated.get('hookSpecificOutput', {}).get('additionalContext'):
                        raise RuntimeError('Identical context was delivered twice')
                    passed(reader + ':no-repeated-context')

                async def transport():
                    saved = await _mcp(memory, repo, 'claude', 'cortex_task', {'action': 'save',
                        'title': 'Prova de retomada', 'summary': 'Memória de teste entre processos.', 'next_step': 'Confirmar leitura no outro cliente.'})
                    read = await _mcp(memory, repo, 'codex', 'cortex_task', {'action': 'resume', 'task_id': saved['id']})
                    if read.get('summary') != 'Memória de teste entre processos.':
                        raise RuntimeError('MCP checkpoint did not survive reconnection')
                asyncio.run(asyncio.wait_for(transport(), timeout=40))
                passed('mcp:shared-checkpoint-after-reconnection')
                from cortex_claude.reliability import backups
                snapshot = backups.create(memory)
                backups.test_restore(memory, snapshot['id'])
                passed('backup:restore-and-integrity')
                result['status'] = 'passed'
        except Exception as error:
            result['checks'].append({'name': 'round-trip', 'passed': False, 'error': type(error).__name__})
        result.update(completed_at=time.time(), elapsed_ms=round((time.time() - started) * 1000))
        write_json(root / 'probe.json', result)
    return result
