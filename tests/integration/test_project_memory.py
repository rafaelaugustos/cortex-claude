import json
import sqlite3

import pytest
import sqlite_vec

from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.learning.projects import add_note, inspect_project, project_detail, read_project, refresh_project
from cortex_claude.learning.store import LearningStore
from cortex_claude.storage.database import StorageManager
from cortex_claude.storage.migrations import initialize_schema


def project(path):
    path.mkdir(parents=True)
    (path / '.git').mkdir()
    (path / 'package.json').write_text(json.dumps({'name': 'orders', 'description': 'Manage customer orders', 'dependencies': {'vue': '3'}, 'scripts': {'test': 'vitest', 'build': 'touch SHOULD_NOT_EXIST'}}))
    (path / 'README.md').write_text('# Orders\n## Architecture\nThe parser is in parser.py.\n')
    (path / 'parser.py').write_text('def parse(value):\n    return value.strip()\n')
    return str(path)


def test_project_memory_is_scoped_in_one_store_bounded_and_deduplicated(tmp_path):
    a, b = project(tmp_path / 'a' / 'orders'), project(tmp_path / 'b' / 'orders')
    with LearningStore(tmp_path / 'memory') as store:
        first = refresh_project(store, a)
        assert refresh_project(store, a)['revision'] == first['revision']
        refresh_project(store, b)
        add_note(store, a, 'architecture', 'The parser strips surrounding whitespace from orders.', ['parser.py'])
        assert not project_detail(store, b)['notes']
        result = store.context('Explain the project architecture for orders', a, 'first')
        assert result['tokens'] <= store.config.max_context_tokens
        assert 'orders' in result['context']
        assert 'strips surrounding whitespace' in result['context']
        assert store.context('Explain the project architecture for orders', a, 'first')['tokens'] == 0
        assert store.context('obrigado', a, 'other')['tokens'] == 0
        assert store.context('Explain the project architecture', b, 'b')['tokens'] > 0
        assert store.context('Explain the project architecture', str(tmp_path / 'unseen'), 'x')['tokens'] == 0
        store.session('first', a, reset=True)
        assert store.context('Explain the project architecture', a, 'first')['tokens'] > 0
        result = read_project(store, a, 250)
        assert count_tokens(json.dumps(result, ensure_ascii=False)) <= 250
        assert store.conn.execute('SELECT COUNT(*) FROM project_profiles').fetchone()[0] == 2
    assert not (tmp_path / 'a/orders/SHOULD_NOT_EXIST').exists()


def test_changed_sources_suspend_conclusions_until_revalidated(tmp_path):
    root = tmp_path / 'repo'
    cwd = project(root)
    with LearningStore(tmp_path / 'memory') as store:
        refresh_project(store, cwd)
        content = 'The parser strips surrounding whitespace from orders.'
        note = add_note(store, cwd, 'architecture', content, ['parser.py'])
        assert not project_detail(store, cwd)['notes'][0]['needs_review']
        (root / 'parser.py').write_text('def parse(value):\n    return value\n')
        assert project_detail(store, cwd)['notes'][0]['needs_review']
        assert 'whitespace' not in store.context('Explain project whitespace parser', cwd, delivered=False)['context']
        refresh_project(store, cwd)
        assert project_detail(store, cwd)['notes'][0]['needs_review']
        # Re-reading manifests cannot validate an architectural assertion.
        (root / 'package.json').write_text('{"name":"orders-new"}')
        assert project_detail(store, cwd)['needs_review']
        assert not store.context('Explain project parser', cwd, delivered=False)['context']
        refresh_project(store, cwd)
        assert add_note(store, cwd, 'architecture', content, ['parser.py'])['id'] == note['id']
        assert not project_detail(store, cwd)['notes'][0]['needs_review']


def test_scanner_avoids_secrets_generated_files_and_external_symlinks(tmp_path):
    root = tmp_path / 'repo'
    cwd = project(root)
    (root / '.env').write_text('PASSWORD=DO_NOT_READ')
    (root / 'node_modules').mkdir()
    (root / 'node_modules/package.json').write_text('{"name":"DO_NOT_READ"}')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'package.json').write_text('{"name":"DO_NOT_READ"}')
    (root / 'linked').symlink_to(outside, target_is_directory=True)
    (root / 'README.md').write_text('# Public\n<private>\n## DO_NOT_READ\n</private>\n')
    _, data, sources = inspect_project(cwd)
    assert 'DO_NOT_READ' not in json.dumps(data)
    assert set(sources) == {'package.json', 'README.md'}
    with LearningStore(tmp_path / 'memory') as store:
        for paths in [['../outside/package.json'], ['.env'], ['node_modules/package.json']]:
            with pytest.raises(ValueError):
                add_note(store, cwd, 'architecture', 'Unsupported conclusion', paths)
        with pytest.raises(ValueError):
            add_note(store, cwd, 'architecture', 'Command: grep parser Result: stdout', ['parser.py'])


def test_execution_migration_preserves_history_and_removes_search_pollution(tmp_path):
    storage = StorageManager(tmp_path)
    conn = storage.get_database('global')
    vector = sqlite_vec.serialize_float32([.1] * 384)
    for ident, text, tags in [('noise', 'Command: grep UNIQUE_NOISE Result: fix error', '["auto-capture","bash"]'), ('useful', 'Run npm test to validate orders before publishing', '[]'), ('manual', 'Command: npm test validates changes', '[]')]:
        conn.execute("INSERT INTO memories(id,content,tags,scope,created_at,updated_at,accessed_at,cluster_id) VALUES (?,?,?,'global',1,1,1,1)", (ident,text,tags))
        conn.execute("INSERT INTO memory_vectors VALUES (?,?)", (ident,vector))
    conn.execute("INSERT INTO clusters(id,scope,label,member_count,updated_at) VALUES (1,'global','command string status',3,1)")
    conn.execute("INSERT INTO facts(id,subject,relation,object,source_memory_id,scope,created_at) VALUES ('noise-fact','command','returns','noise','noise','global',1)")
    conn.execute('UPDATE schema_version SET version=8')
    conn.commit()
    before = dict(conn.execute("SELECT * FROM memories WHERE id='noise'").fetchone())
    initialize_schema(conn)
    initialize_schema(conn)
    assert dict(conn.execute('SELECT * FROM execution_history').fetchone()) == before
    assert conn.execute('SELECT embedding FROM execution_vectors').fetchone()[0] == vector
    assert conn.execute('SELECT id FROM execution_facts').fetchone()[0] == 'noise-fact'
    assert conn.execute("SELECT COUNT(*) FROM memories_fts WHERE memories_fts MATCH 'UNIQUE_NOISE'").fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM memory_vectors').fetchone()[0] == 2
    assert {row[0] for row in conn.execute('SELECT id FROM memories')} == {'useful','manual'}
    assert conn.execute('SELECT COUNT(*) FROM clusters').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM facts').fetchone()[0] == 0
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    storage.close_all()


def test_execution_migration_rolls_back_on_archive_failure(tmp_path):
    storage = StorageManager(tmp_path)
    conn = storage.get_database('global')
    conn.execute("INSERT INTO memories(id,content,tags,scope,created_at,updated_at,accessed_at) VALUES ('noise','Bash: grep','[\"auto-capture\"]','global',1,1,1)")
    conn.execute("CREATE TRIGGER reject_history BEFORE INSERT ON execution_history BEGIN SELECT RAISE(ABORT,'test failure'); END")
    conn.execute('UPDATE schema_version SET version=8')
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        initialize_schema(conn)
    assert conn.execute('SELECT version FROM schema_version').fetchone()[0] == 8
    assert conn.execute('SELECT COUNT(*) FROM memories').fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM execution_history').fetchone()[0] == 0
    storage.close_all()
