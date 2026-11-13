import asyncio
import json
import os
import sys

import pytest

from cortex_claude.reliability import probe
from cortex_claude.reliability.files import read_json


def test_checkpoint_reconnects_without_loading_archive_dependencies(tmp_path, monkeypatch):
    """A real MCP subprocess must serve recovery tools without the archive engine."""
    guard = tmp_path / 'guard'
    guard.mkdir()
    (guard / 'sitecustomize.py').write_text('''
import sys
class NoArchiveImports:
    def find_spec(self, fullname, *args):
        if fullname in {'numpy', 'torch', 'spacy', 'sentence_transformers', 'cortex_claude.core.engine'}:
            raise RuntimeError('Recovery must not import ' + fullname)
sys.meta_path.insert(0, NoArchiveImports())
''')
    monkeypatch.setenv('PYTHONPATH', str(guard) + os.pathsep + os.environ.get('PYTHONPATH', ''))
    home, repo = tmp_path / 'memory', tmp_path / 'repo'
    home.mkdir()
    repo.mkdir()
    (home / 'config.json').write_text(json.dumps({'learning': {'semantic_enabled': False}}))

    async def reconnect():
        saved = await probe._mcp(home, repo, 'claude', 'cortex_task', {
            'action': 'save', 'title': 'Restart recovery', 'summary': 'Checkpoint survived.',
            'next_step': 'Verify from another process.',
        })
        resumed = await probe._mcp(home, repo, 'codex', 'cortex_task', {
            'action': 'resume', 'task_id': saved['id'],
        })
        assert resumed['summary'] == 'Checkpoint survived.'

    asyncio.run(asyncio.wait_for(reconnect(), timeout=40))
    state = read_json(home / 'recovery/state.json')
    assert state['mcp_claude_at'] > 0
    assert state['mcp_codex_at'] > 0


def test_archive_tools_still_initialize_the_engine_on_demand(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def scopes():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'cortex_claude'],
                                       env={**os.environ, 'CORTEX_HOME': str(tmp_path)})
        async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
            await session.initialize()
            created = await session.call_tool('cortex_scopes', {'action': 'create', 'name': 'archive-check'})
            assert not created.isError
            listed = await session.call_tool('cortex_scopes', {'action': 'list'})
            assert not listed.isError
            return listed.content[0].text

    result = asyncio.run(asyncio.wait_for(scopes(), timeout=40))
    assert 'archive-check' in result


def test_failed_archive_initialization_can_be_retried(tmp_path, monkeypatch):
    from cortex_claude.core import engine
    from cortex_claude.server import app

    attempts, closed = [], []

    class RecoverableEngine:
        def __init__(self, config):
            attempts.append(self)

        def initialize(self):
            if len(attempts) == 1:
                raise OSError('archive temporarily unavailable')

        def close(self):
            closed.append(self)

    monkeypatch.setenv('CORTEX_HOME', str(tmp_path))
    monkeypatch.setattr(app, 'engine', None)
    monkeypatch.setattr(engine, 'CortexEngine', RecoverableEngine)
    with pytest.raises(OSError, match='temporarily unavailable'):
        app._get_engine()
    assert closed == [attempts[0]]
    assert app._get_engine() is attempts[1]
    assert app._get_engine() is attempts[1]
    assert len(attempts) == 2
