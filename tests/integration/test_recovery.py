import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import tempfile
from pathlib import Path

import pytest

from cortex_claude.learning.store import LearningStore
from cortex_claude.learning.projects import add_note, project_detail, refresh_project
from cortex_claude.learning.tasks import list_tasks, save_task, update_state
from cortex_claude.reliability import backups
from cortex_claude.reliability.checkpoints import capture, startup_context
from cortex_claude.reliability.clients import configure_toml, install_codex
from cortex_claude.reliability.events import apply, normalize
from cortex_claude.reliability.files import read_json, write_json
from cortex_claude.reliability.queue import drain, enqueue, pending, retry
from cortex_claude.reliability.services import prepare


@pytest.fixture
def environment(tmp_path):
    with tempfile.TemporaryDirectory(prefix='cx-rec-', dir='/tmp') as directory:
        home, repo = Path(directory).resolve() / 'memory', Path(directory).resolve() / 'repo'
        home.mkdir(); repo.mkdir()
        (home / 'config.json').write_text(json.dumps({'learning': {'semantic_enabled': False}, 'clustering': {'enabled': False}, 'reliability': {'auto_backup': False, 'backup_keep': 2}}))
        (repo / 'package.json').write_text('{"name":"orders"}')
        (repo / 'parser.py').write_text('def parse(value):\n    return value.strip()\n')
        yield home, repo


def event(home, repo, name, client='claude', **fields):
    data = normalize(name, {'session_id': 'thread', 'cwd': str(repo), **fields}, client)
    ident = enqueue(home, 'hook', {'event': name, 'data': data})
    drain(home, lambda job: apply(home, job), kinds={'hook'})
    return ident, data


def test_committed_effect_before_crash_is_replayed_once(environment):
    home, repo = environment
    writer = '''
import json,os,signal,sys
from pathlib import Path
from cortex_claude.reliability.queue import enqueue,pending
from cortex_claude.reliability.events import apply,normalize
h,r=map(Path,sys.argv[1:])
data=normalize('UserPromptSubmit',{'session_id':'thread','cwd':str(r),'prompt':'Sempre prefiro funções pequenas'},'claude')
enqueue(h,'hook',{'event':'UserPromptSubmit','data':data},'deterministic-event')
apply(h,pending(h)[0])
os.kill(os.getpid(),signal.SIGKILL)
'''
    result = subprocess.run([sys.executable, '-c', writer, str(home), str(repo)], env={**os.environ, 'CORTEX_HOME': str(home)}, timeout=15)
    assert result.returncode == -signal.SIGKILL
    assert len(pending(home)) == 1
    drain(home, lambda job: apply(home, job))
    assert not pending(home)
    with LearningStore(home) as store:
        assert store.list()[0]['confirmations'] == 1
        assert list_tasks(store)[0]['revision'] == 1
        assert store.conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_failed_jobs_retry_in_order_without_losing_other_sessions(environment):
    home, repo = environment
    for sid, name in [('a', 'first'), ('a', 'second'), ('b', 'other')]:
        enqueue(home, 'test', {'session_id': sid, 'name': name})
    seen = []
    def fail(job):
        if job['payload']['name'] == 'first':
            raise sqlite3.OperationalError('database is locked')
        seen.append(job['payload']['name'])
    result = drain(home, fail)
    assert result['errors'] == 1 and seen == ['other']
    assert len(pending(home)) == 2
    drain(home, lambda job: seen.append(job['payload']['name']))
    assert seen == ['other']
    retry(home)
    drain(home, lambda job: seen.append(job['payload']['name']))
    assert seen == ['other', 'first', 'second'] and not pending(home)


def test_malformed_pending_record_is_preserved_and_other_jobs_continue(environment):
    home, _ = environment
    ident = enqueue(home, 'test', {'session_id': 'a'})
    path = home / 'recovery' / 'pending' / f'{ident}.json'
    damaged = json.dumps({'id': ident, 'payload': {'data': []}, 'kind': 'hook'})
    path.write_text(damaged)
    other = enqueue(home, 'test', {'session_id': 'b'})
    seen = []
    result = drain(home, lambda job: seen.append(job['id']))
    assert seen == [other] and result['errors'] == 1
    assert path.read_text() == damaged
    assert pending(home)[0]['error'] == 'InvalidJob'


def test_partial_checkpoint_survives_client_switch_and_flags_changed_sources(environment):
    home, repo = environment
    event(home, repo, 'UserPromptSubmit', prompt='Implementar normalização dos pedidos no parser')
    event(home, repo, 'PostToolUse', tool_name='Edit', tool_input={'file_path': str(repo / 'parser.py')}, tool_response='private tool output')
    event(home, repo, 'Stop', last_assistant_message='A normalização está implementada. Ainda faltam os testes.')
    with LearningStore(home) as store:
        item = list_tasks(store, str(repo))[0]
        assert item['source'] == 'automatic' and item['client'] == 'claude'
        assert 'não verificado' in item['summary'] and 'faltam' in item['summary']
        assert not item['needs_review']
        store.session('codex:new', str(repo))
        output = startup_context(store, str(repo), 'codex:new')
        assert item['id'] in output['hookSpecificOutput']['additionalContext']
        assert not startup_context(store, str(repo), 'codex:new')
    (repo / 'parser.py').write_text('changed = True\n')
    with LearningStore(home) as store:
        assert list_tasks(store, str(repo))[0]['needs_review']


def test_old_events_do_not_overwrite_newer_or_manual_checkpoints(environment):
    home, repo = environment
    data = normalize('UserPromptSubmit', {'session_id': 's', 'cwd': str(repo), 'prompt': 'Implement orders parser'}, 'codex')
    with LearningStore(home) as store:
        capture(store, 'UserPromptSubmit', data, 'new', 100)
        capture(store, 'UserPromptSubmit', {**data, 'prompt': 'OLD REQUEST'}, 'old', 50)
        item = list_tasks(store)[0]
        assert 'OLD' not in item['summary']
        save_task(store, str(repo), 'codex:s', task_id=item['id'], expected_revision=item['revision'], title='Reviewed task', summary='Verified meaningful summary', next_step='Run tests')
        capture(store, 'Stop', {**data, 'last_assistant_message': 'Wrong overwrite'}, 'later', 150)
        assert list_tasks(store)[0]['summary'] == 'Verified meaningful summary'
        item = list_tasks(store)[0]
        update_state(store, item['id'], 'forget', item['revision'])
        capture(store, 'Stop', {**data, 'last_assistant_message': 'Do not resurrect'}, 'last', 200)
        assert not list_tasks(store)


def test_event_normalization_excludes_tool_dumps_private_spans_and_patch_bodies(environment):
    _, repo = environment
    value = normalize('PostToolUse', {'cwd': str(repo), 'session_id': 's', 'tool_name': 'Bash', 'tool_input': {'command': 'python -m pytest'}, 'tool_response': {'stdout': 'secret stdout\n17 passed', 'exit_code': 0}}, 'codex')
    assert value['session_id'] == 'codex:s'
    assert value['tool_response']['stdout'] == '17 passed'
    patch = normalize('PostToolUse', {'cwd': str(repo), 'tool_name': 'apply_patch', 'tool_input': {'command': '*** Update File: parser.py\n+secret content\n*** End Patch'}}, 'codex')
    assert patch['changed_files'] == [str(repo / 'parser.py')]
    assert 'secret' not in json.dumps(patch)
    prompt = normalize('UserPromptSubmit', {'cwd': str(repo), 'prompt': 'Implement parser <private>hidden <private>nested</private>also hidden</private> now'}, 'claude')
    assert 'hidden' not in prompt['prompt'] and 'nested' not in prompt['prompt']


def seed(home, repo):
    with LearningStore(home) as store:
        refresh_project(store, str(repo))
        add_note(store, str(repo), 'architecture', 'The parser normalizes order values.', ['parser.py'])
        save_task(store, str(repo), 's', title='Orders', summary='Parser extracted', next_step='Run tests')


def test_backup_restores_wal_data_and_pending_operations_without_overwriting_live_data(environment, tmp_path):
    home, repo = environment
    seed(home, repo)
    enqueue(home, 'hook', {'event': 'Stop', 'data': {'session_id': 's', 'cwd': str(repo)}})
    result = backups.create(home)
    assert result['verified']
    assert backups.test_restore(home, result['id'])['verified']
    destination = tmp_path / 'recovered'
    backups.restore(home, result['id'], destination)
    with LearningStore(destination) as store:
        assert project_detail(store, str(repo))['notes'][0]['content'] == 'The parser normalizes order values.'
        assert list_tasks(store)[0]['next_step'] == 'Run tests'
    assert len(pending(destination)) == 1
    with pytest.raises(ValueError, match='must not exist'):
        backups.restore(home, result['id'], home)


def test_corrupt_backup_is_rejected_and_retention_only_removes_completed_snapshots(environment, tmp_path):
    home, repo = environment
    seed(home, repo)
    first = backups.create(home)['id']
    second = backups.create(home)['id']
    third = backups.create(home)['id']
    assert {item['id'] for item in backups.snapshots(home)} == {second, third}
    assert not (home / 'backups' / first).exists()
    (home / 'backups' / third / 'learning.db').write_bytes(b'broken')
    with pytest.raises(ValueError, match='checksum'):
        backups.restore(home, third, tmp_path / 'must-not-exist')
    assert not (tmp_path / 'must-not-exist').exists()
    assert backups.validate(home / 'backups' / second)


def test_backup_failure_preserves_previous_snapshot(environment, monkeypatch):
    home, repo = environment
    seed(home, repo)
    first = backups.create(home)
    def disk_full(*args):
        raise OSError('No space left on device')
    monkeypatch.setattr(backups, '_copy_database', disk_full)
    with pytest.raises(OSError):
        backups.create(home)
    assert backups.snapshots(home)[0]['id'] == first['id']
    assert read_json(home / 'recovery/state.json')['backup_error']['type'] == 'OSError'
    assert not list((home / 'backups').glob('.snapshot-*'))


def test_codex_setup_preserves_user_settings_and_does_not_trust_hooks(environment, tmp_path):
    import tomllib
    home, _ = environment
    directory = tmp_path / 'codex'; directory.mkdir()
    original = '# keep comment\nmodel = "example"\n[mcp_servers.other]\ncommand = "keep"\n[mcp_servers.cortex]\ncommand = "old"\n[mcp_servers.cortex.env]\nKEEP = "yes"\n'
    (directory / 'config.toml').write_text(original)
    (directory / 'AGENTS.md').write_text('# My rules\nPreserve this.\n')
    (directory / 'hooks.json').write_text('{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"user-stop"}]}]}}')
    install_codex(home, directory, '/example/python')
    first = {name: (directory / name).read_text() for name in ('config.toml', 'hooks.json', 'AGENTS.md')}
    result = install_codex(home, directory, '/example/python')
    assert result['review_required']
    assert first == {name: (directory / name).read_text() for name in first}
    value = tomllib.loads(first['config.toml'])
    assert value['model'] == 'example' and value['mcp_servers']['other']['command'] == 'keep'
    assert value['mcp_servers']['cortex']['env']['KEEP'] == 'yes'
    assert 'Preserve this.' in first['AGENTS.md'] and '# keep comment' in first['config.toml']
    assert json.loads(first['hooks.json'])['hooks']['Stop'][0]['hooks'][0]['command'] == 'user-stop'
    assert not any('trust' in path.name for path in directory.iterdir())
    with pytest.raises(ValueError):
        configure_toml('invalid = [', '/python', home)


def test_service_definitions_pin_interpreter_and_restart_on_login(environment, tmp_path):
    import plistlib
    home, _ = environment
    paths = prepare(home, tmp_path / 'agents', '/installed/python')
    for path in paths:
        value = plistlib.loads(path.read_bytes())
        assert value['KeepAlive'] and value['RunAtLoad']
        assert value['ProgramArguments'][0] == '/installed/python'
        assert value['EnvironmentVariables']['CORTEX_HOME'] == str(home)
        assert value['ExitTimeOut'] >= 15


def test_daemon_restart_drains_persisted_events_and_rejects_duplicate_instance(environment):
    home, repo = environment
    data = normalize('UserPromptSubmit', {'session_id': 'recover', 'cwd': str(repo), 'prompt': 'Implementar parser de pedidos'}, 'codex')
    enqueue(home, 'hook', {'event': 'UserPromptSubmit', 'data': data})
    env = {**os.environ, 'CORTEX_HOME': str(home)}
    from cortex_claude.reliability.health import ping
    def start():
        child = subprocess.Popen([sys.executable, '-m', 'cortex_claude', 'daemon'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise AssertionError('Daemon exited unexpectedly')
            if ping(home).get('status') == 'running' and not pending(home):
                return child
            time.sleep(.1)
        child.kill(); child.wait()
        raise AssertionError('Daemon startup timed out')
    first = start()
    try:
        duplicate = subprocess.run([sys.executable, '-m', 'cortex_claude', 'daemon'], env=env, timeout=5)
        assert duplicate.returncode == 0 and ping(home)['ok']
    finally:
        first.kill(); first.wait(timeout=5)
    assert (home / 'cortex.sock').exists()  # stale endpoint left by SIGKILL
    second = start()
    try:
        with LearningStore(home) as store:
            assert list_tasks(store)[0]['source'] == 'automatic'
    finally:
        second.terminate(); second.wait(timeout=20)
    assert not (home / 'cortex.sock').exists()
def test_service_registration_retries_transient_launchd_error(environment, monkeypatch):
    import subprocess
    from cortex_claude.reliability import services
    home, _ = environment
    calls = []
    monkeypatch.setattr(services.sys, 'platform', 'darwin')
    monkeypatch.setattr(services, 'prepare', lambda *args: [home / (label + '.plist') for label in services.LABELS.values()])
    monkeypatch.setattr(services, 'stop_recorded', lambda *args: False)
    monkeypatch.setattr(services.time, 'sleep', lambda seconds: None)
    def run(args, **kwargs):
        calls.append(args)
        if args[1] == 'print':
            return subprocess.CompletedProcess(args, 1)
        count = sum(c[1] == 'bootstrap' for c in calls)
        return subprocess.CompletedProcess(args, 5 if count == 1 else 0)
    monkeypatch.setattr(services.subprocess, 'run', run)
    assert services.install(home)['installed']
    assert sum(c[1] == 'bootstrap' for c in calls) == 3
