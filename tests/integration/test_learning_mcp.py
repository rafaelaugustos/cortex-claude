import json
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_new_tools_work_over_the_actual_mcp_transport(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "example.py").write_text("value = 1\n")
    (repo / "pyproject.toml").write_text('[project]\nname = "example"\ndescription = "A parser"\n')
    params = StdioServerParameters(command=sys.executable, args=["-m", "cortex_claude"], cwd=str(repo), env={**os.environ, "CORTEX_HOME": str(tmp_path / "memory")})
    async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
        await client.initialize()
        names = {tool.name for tool in (await client.list_tools()).tools}
        assert {"cortex_learn", "cortex_read", "cortex_task"} <= names
        assert "cortex_project" in names
        assert len(names) == 14
        async def call(name, args):
            result = await client.call_tool(name, args)
            assert not result.isError
            return json.loads(result.content[0].text)
        args = {"path": "example.py", "session_id": "mcp-reader"}
        assert (await call("cortex_read", args))["mode"] == "full"
        assert (await call("cortex_read", args))["mode"] == "unchanged"
        task = await call("cortex_task", {"action": "save", "title": "Example", "summary": "Parser ready", "next_step": "Run tests", "dependencies": ["example.py"]})
        resumed = await call("cortex_task", {"action": "resume", "task_id": task["id"]})
        assert resumed["summary"] == "Parser ready" and not resumed["needs_review"]
        await call("cortex_task", {"action": "complete", "task_id": task["id"], "expected_revision": task["revision"]})
        assert (await call("cortex_task", {"action": "list"}))[0]["state"] == "complete"
        project = await call("cortex_project", {"action": "refresh"})
        assert project["name"] == "example"
        await call("cortex_project", {"action": "note", "section": "architecture", "content": "example.py defines the parser value.", "sources": ["example.py"]})
        project = await call("cortex_project", {"max_tokens": 1500})
        assert project["notes"][0]["sources"] == ["example.py"]


@pytest.mark.asyncio
async def test_claude_and_codex_share_sourced_memory_over_separate_mcp_processes(tmp_path):
    repo, home = tmp_path / 'repo', tmp_path / 'memory'
    repo.mkdir(); home.mkdir()
    (home / 'config.json').write_text('{"learning":{"semantic_enabled":false}}')
    (repo / 'package.json').write_text('{"name":"orders"}')
    (repo / 'parser.py').write_text('def parse(value): return value.strip()\n')
    task_id = None
    for name in ('claude', 'codex', 'claude'):
        params = StdioServerParameters(command=sys.executable, args=['-m', 'cortex_claude'], cwd=str(repo), env={**os.environ, 'CORTEX_HOME': str(home), 'CORTEX_CLIENT': name})
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            async def call(tool, args):
                result = await client.call_tool(tool, args)
                assert not result.isError
                return json.loads(result.content[0].text)
            if task_id is None:
                await call('cortex_project', {'action': 'refresh'})
                await call('cortex_project', {'action': 'note', 'section': 'architecture', 'content': 'parser.py normalizes order values.', 'sources': ['parser.py']})
                task_id = (await call('cortex_task', {'action': 'save', 'title': 'Orders', 'summary': 'Normalization extracted', 'next_step': 'Test empty input', 'dependencies': ['parser.py']}))['id']
            else:
                project = await call('cortex_project', {'max_tokens': 1500})
                assert project['notes'][0]['content'] == 'parser.py normalizes order values.'
                task = await call('cortex_task', {'action': 'resume', 'task_id': task_id})
                assert not task['needs_review']
                if name == 'codex':
                    assert task['next_step'] == 'Test empty input'
                    await call('cortex_task', {'action': 'save', 'task_id': task_id, 'expected_revision': task['revision'], 'title': 'Orders', 'summary': 'Empty input checked', 'next_step': 'Integrate consumer'})
                else:
                    assert task['summary'] == 'Empty input checked' and task['next_step'] == 'Integrate consumer'
