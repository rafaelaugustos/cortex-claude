import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from cortex_claude.storage.database import StorageManager
from cortex_claude.web import server as web


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'CORTEX_HOME', tmp_path)
    server = ThreadingHTTPServer(('127.0.0.1', 0), web.CortexHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(method, path, body=None):
        connection = HTTPConnection(*server.server_address, timeout=5)
        try:
            connection.request(method, path, json.dumps(body) if body else None)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    yield tmp_path, request
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.mark.parametrize(('method', 'path', 'body'), [
    ('GET', '/api/learning', None),
    ('GET', '/api/projects', None),
    ('GET', '/api/tasks', None),
    ('GET', '/api/conflicts', None),
    ('POST', '/api/tasks/task:test', {'action': 'complete', 'expected_revision': 1}),
    ('DELETE', '/api/learning/test', None),
])
def test_unreadable_learning_returns_actionable_error_and_preserves_file(dashboard, method, path, body):
    home, request = dashboard
    damaged = home / 'learning.db'
    original = b'unreadable sqlite contents'
    damaged.write_bytes(original)

    status, headers, data = request(method, path, body)

    assert status == 503
    assert headers['Cache-Control'] == 'no-store'
    assert 'Recuperação' in data['error']
    assert str(home) not in data['error']
    assert damaged.read_bytes() == original
    status, _, health = request('GET', '/api/health')
    assert status == 200
    assert health['status'] == 'attention'
    assert {'name': 'learning.db', 'readable': False} in health['databases']


@pytest.mark.parametrize('path', ['/api/overview', '/api/memories', '/api/clusters', '/api/executions'])
def test_broken_scope_cannot_look_like_complete_or_empty_results(dashboard, path):
    home, request = dashboard
    storage = StorageManager(home)
    storage.get_database('global')
    storage.get_database('project:broken')
    storage.close_all()
    (home / 'scopes/project__broken.db').write_bytes(b'broken database')

    status, _, data = request('GET', path)

    assert status == 503
    assert 'error' in data
    assert 'items' not in data


def test_backup_access_failure_is_unavailable_not_invalid_input(dashboard, monkeypatch):
    from cortex_claude.reliability import backups
    _, request = dashboard

    def denied(*args):
        raise PermissionError('cannot open backup directory')

    monkeypatch.setattr(backups, 'create', denied)
    status, _, data = request('POST', '/api/recovery/backup')
    assert status == 503
    assert 'Recuperação' in data['error']


def test_invalid_project_input_still_returns_bad_request(dashboard):
    _, request = dashboard
    status, _, _ = request('POST', '/api/projects/refresh', {'origin': 'relative-path'})
    assert status == 400
