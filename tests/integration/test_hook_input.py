import json
import os
import subprocess
import sys

import pytest

from cortex_claude.reliability.events import apply
from cortex_claude.reliability.files import lock
from cortex_claude.reliability.health import report
from cortex_claude.reliability.hook_input import MAX_HOOK_INPUT_BYTES
from cortex_claude.reliability.queue import drain, pending


@pytest.fixture
def memory(tmp_path):
    (tmp_path / 'config.json').write_text(json.dumps({
        'learning': {'semantic_enabled': False},
        'reliability': {'auto_backup': False},
    }))
    return tmp_path


def invoke(home, payload, client='codex'):
    return subprocess.run(
        [sys.executable, '-m', 'cortex_claude', 'hook', 'PostToolUse', client],
        input=payload, capture_output=True, timeout=10,
        env={**os.environ, 'CORTEX_HOME': str(home)},
    )


@pytest.mark.parametrize('client', ['claude', 'codex'])
@pytest.mark.parametrize('character', ['x', '🧠'])
def test_large_valid_event_is_normalized_and_durably_queued(memory, client, character):
    # The private span crosses the old read limit; useful fields follow the large output.
    payload = json.dumps({
        'tool_response': {'stdout': '<private>PRIVATE_SENTINEL' + character * 1_000_050 + '</private>\n3 passed', 'exit_code': 0},
        'tool_name': 'Bash', 'tool_input': {'command': 'python -m pytest tests/'},
        'session_id': 'large-event', 'tool_use_id': 'large-call', 'cwd': str(memory),
    }, ensure_ascii=False).encode('utf-8')
    with lock(memory / 'recovery/worker.lock'):
        result = invoke(memory, payload, client)
        assert result.returncode == 0, result.stderr
        assert not (memory / 'hook-error.log').exists(), result.stdout
        jobs = pending(memory)
        assert len(jobs) == 1
        data = jobs[0]['payload']['data']
        assert data['client'] == client
        assert data['tool_response'] == {'stdout': '3 passed', 'exit_code': 0, 'interrupted': False}
        stored = (memory / 'recovery/pending' / f"{jobs[0]['id']}.json").read_text()
        assert 'PRIVATE_SENTINEL' not in stored and len(stored) < 2000
    assert drain(memory, lambda job: apply(memory, job))['processed'] == 1
    assert not pending(memory)
    assert len(list((memory / 'recovery/receipts').glob('*.json'))) == 1


@pytest.mark.parametrize('client', ['claude', 'codex'])
@pytest.mark.parametrize('case, expected_type, expected_stage', [
    ('oversized', 'HookInputTooLarge', 'read_input'),
    ('malformed', 'JSONDecodeError', 'parse_input'),
    ('encoding', 'UnicodeDecodeError', 'parse_input'),
    ('empty', 'JSONDecodeError', 'parse_input'),
])
def test_rejected_input_reports_stage_without_persisting_private_data(memory, client, case, expected_type, expected_stage):
    payload = {
        'oversized': b'{"private":"PRIVATE_SENTINEL"}' + b' ' * MAX_HOOK_INPUT_BYTES,
        'malformed': b'{"private":"PRIVATE_SENTINEL",',
        'encoding': b'{"private":"PRIVATE_SENTINEL\xff"}',
        'empty': b'',
    }[case]
    result = invoke(memory, payload, client)
    assert result.returncode == 0
    message = json.loads(result.stdout)['systemMessage']
    assert 'não foi salvo' in message
    assert '8 MiB' in message if case == 'oversized' else expected_type in message
    assert not pending(memory)
    assert not list((memory / 'recovery/receipts').glob('*.json'))
    diagnostic = json.loads((memory / 'recovery/hook-error.json').read_text())
    assert diagnostic['stage'] == expected_stage and diagnostic['type'] == expected_type
    assert diagnostic['client'] == client and diagnostic['event'] == 'PostToolUse'
    assert diagnostic['input_bytes_read'] == min(len(payload), MAX_HOOK_INPUT_BYTES + 1)
    for path in memory.rglob('*'):
        if path.is_file():
            assert b'PRIVATE_SENTINEL' not in path.read_bytes()
    assert b'PRIVATE_SENTINEL' not in result.stdout + result.stderr
    health = report(memory)
    assert health['hook_error'] == diagnostic
    assert any('não foi salvo' in issue for issue in health['issues'])


def test_later_json_failure_is_not_mislabeled_as_invalid_input(memory):
    (memory / 'config.json').write_text('{"PRIVATE_CONFIG":')
    result = invoke(memory, json.dumps({'cwd': str(memory), 'tool_name': 'Read'}).encode())
    assert result.returncode == 0
    diagnostic = json.loads((memory / 'recovery/hook-error.json').read_text())
    assert diagnostic['type'] == 'JSONDecodeError'
    assert diagnostic['stage'] == 'context'
    assert 'etapa: context' in json.loads(result.stdout)['systemMessage']
    assert len(pending(memory)) == 1  # This event did reach durable storage.
    assert 'PRIVATE_CONFIG' not in json.dumps(diagnostic)


def test_unreadable_hook_diagnostic_preserves_the_legacy_health_warning(memory):
    (memory / 'recovery').mkdir()
    (memory / 'recovery/hook-error.json').write_text('{')
    (memory / 'hook-error.log').write_text('PostToolUse: JSONDecodeError\n')
    health = report(memory)
    assert health['hook_error'] == {}
    assert any('Um hook não conseguiu confirmar' in issue for issue in health['issues'])


def test_old_metadata_does_not_mislabel_a_new_legacy_error(memory):
    (memory / 'recovery').mkdir()
    (memory / 'recovery/hook-error.json').write_text(json.dumps({
        'type': 'HookInputTooLarge', 'stage': 'read_input', 'at': 1,
    }))
    (memory / 'hook-error.log').write_text('PostToolUse: JSONDecodeError\n')
    health = report(memory)
    assert health['hook_error'] == {}
    assert not any('8 MiB' in issue for issue in health['issues'])
    assert any('Um hook não conseguiu confirmar' in issue for issue in health['issues'])
