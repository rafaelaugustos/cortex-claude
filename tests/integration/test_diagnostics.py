import copy
import io
import json
from pathlib import Path

from cortex_claude.reliability import diagnostics, health, probe
from cortex_claude.reliability.files import read_json


def test_probe_cross_process_preserves_live_data_and_does_not_mark_client_active(tmp_path):
    (tmp_path / 'learning.db').write_bytes(b'untouched live database')
    result = probe.run(tmp_path)
    assert result['status'] == 'passed', result
    assert len(result['checks']) == 8
    assert result['client_activation_tested'] is False
    assert (tmp_path / 'learning.db').read_bytes() == b'untouched live database'
    assert not (tmp_path / 'recovery/state.json').exists()
    assert not list((tmp_path / 'recovery').glob('probe-*'))
    assert read_json(tmp_path / 'recovery/probe.json')['status'] == 'passed'


def test_diagnostics_records_incidents_and_recovery_without_repeating_events(tmp_path, monkeypatch):
    state = {'daemon': {'running': True}, 'databases': [{'readable': True}],
             'queue': {'failures': 0, 'oldest_at': None}, 'policy': {'auto_backup': False},
             'heartbeat_at': None, 'clients': {}}
    monkeypatch.setattr(health, 'report', lambda home: copy.deepcopy(state))
    monkeypatch.setattr(diagnostics, 'urlopen', lambda *args, **kwargs: io.BytesIO(json.dumps({**state, 'instance': diagnostics.identity(tmp_path)}).encode()))
    first = diagnostics.sample(tmp_path)
    assert first['status'] == 'healthy'
    assert len(diagnostics.sample(tmp_path)['events']) == 1
    state['databases'][0]['readable'] = False
    second = diagnostics.sample(tmp_path)
    assert second['codes'] == ['database_unreadable', 'web_access_failure']
    state['databases'][0]['readable'] = True
    final = diagnostics.sample(tmp_path)
    assert len(final['events']) == 3
    assert final['events'][-1]['codes'] == []


def test_monitor_identifies_web_outage_and_unacknowledged_capture(tmp_path, monkeypatch):
    state = {'daemon': {'running': True}, 'databases': [], 'queue': {'failures': 0, 'oldest_at': None},
             'policy': {'auto_backup': False}, 'heartbeat_at': None,
             'clients': {'claude': {'last_received_at': 100, 'last_saved_at': 90}}}
    monkeypatch.setattr(health, 'report', lambda home: state)
    def down(*args, **kwargs):
        raise ConnectionRefusedError()
    monkeypatch.setattr(diagnostics, 'urlopen', down)
    result = diagnostics.sample(tmp_path)
    assert result['codes'] == ['claude_capture_delayed', 'web_unavailable']


def test_diagnostic_exceptions_are_preserved_as_metadata(tmp_path, monkeypatch):
    def denied(home):
        raise PermissionError('private path and contents must not be saved')
    monkeypatch.setattr(health, 'report', denied)
    result = diagnostics.sample(tmp_path)
    assert result['codes'] == ['diagnostic_failed:PermissionError']
    assert 'private path' not in json.dumps(result)
