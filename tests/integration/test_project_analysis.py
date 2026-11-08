import json
from pathlib import Path

from cortex_claude.learning import analysis
from cortex_claude.learning.projects import add_note, project_detail, refresh_project
from cortex_claude.learning.store import LearningStore


def setup(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="orders"\n')
    (root / 'orders.py').write_text('def normalize(value):\n    return value.strip()\ndef submit(value):\n    return normalize(value)\n')
    (root / 'stable.py').write_text('def stable():\n    return 1\n')
    return root


def test_incremental_analysis_reuses_files_and_does_not_revalidate_notes(tmp_path, monkeypatch):
    root = setup(tmp_path)
    with LearningStore(tmp_path / 'memory') as store:
        first = refresh_project(store, str(root))
        assert any(f['caller'] == 'submit' and f['callee'] == 'normalize' for f in first['analysis']['flows'])
        note = add_note(store, str(root), 'architecture', 'Orders remove surrounding whitespace.', ['orders.py'])
        stable = refresh_project(store, str(root))
        assert stable['analysis']['scan']['read_files'] == 0
        assert stable['analysis']['scan']['reused_files'] == 2
        assert refresh_project(store, str(root))['revision'] == stable['revision']
        parsed = []
        extract = analysis._symbols
        monkeypatch.setattr(analysis, '_symbols', lambda path, text: (parsed.append(path), extract(path, text))[1])
        (root / 'orders.py').write_text('def normalize(value):\n    return value\n')
        detail = project_detail(store, str(root))
        assert detail['needs_review']
        assert not detail['analysis']['flows']
        assert detail['review_queue'][0]['id'] == note['id']
        after = refresh_project(store, str(root))
        assert parsed == ['orders.py']
        assert after['analysis']['scan']['read_files'] == 1
        assert after['analysis']['scan']['reused_files'] == 1
        assert after['notes'][0]['needs_review']
        assert after['revision'] > stable['revision']
        (root / 'stable.py').unlink()
        after = refresh_project(store, str(root))
        assert after['analysis']['scan']['removed'] == ['stable.py']
        assert {f['path'] for f in after['analysis']['files']} == {'orders.py'}


def test_new_sources_and_manifests_are_discovered(tmp_path):
    root = setup(tmp_path)
    with LearningStore(tmp_path / 'memory') as store:
        refresh_project(store, str(root))
        (root / 'new.py').write_text('def added():\n    return 2\n')
        (root / 'package.json').write_text('{"name":"orders-web","dependencies":{"vue":"3"}}')
        result = refresh_project(store, str(root))
        assert 'new.py' in result['analysis']['scan']['changed']
        assert any(m['name'] == 'orders-web' for m in result['modules'])


def test_analysis_does_not_capture_private_code_or_external_symlinks(tmp_path):
    root = setup(tmp_path)
    (root / 'private.py').write_text('<private>\ndef SECRET_SYMBOL(): pass\n</private>\n')
    outside = tmp_path / 'outside.py'
    outside.write_text('def OUTSIDE_SYMBOL(): pass\n')
    (root / 'linked.py').symlink_to(outside)
    with LearningStore(tmp_path / 'memory') as store:
        result = refresh_project(store, str(root))
        assert 'SECRET_SYMBOL' not in json.dumps(result)
        assert 'OUTSIDE_SYMBOL' not in json.dumps(result)
        (root / 'orders.py').unlink()
        (root / 'orders.py').symlink_to(outside)
        result = project_detail(store, str(root))
        assert 'orders.py' in result['changed_files']
        assert all(f['path'] != 'orders.py' for f in result['analysis']['files'])


def test_analysis_exposes_limits_and_missing_parsers(tmp_path, monkeypatch):
    root = setup(tmp_path)
    (root / 'main.ts').write_text('export function hello() {}')
    monkeypatch.setattr(analysis, '_get_parser', lambda language: None)
    monkeypatch.setattr(analysis, 'MAX_FILES', 2)
    with LearningStore(tmp_path / 'memory') as store:
        result = refresh_project(store, str(root))
        assert result['analysis']['coverage']['partial']
        assert result['analysis']['coverage']['discovered'] == 3
        assert result['analysis']['coverage']['parser_unavailable'] == 1


def test_vue_setup_symbols_keep_original_source_lines(tmp_path):
    root = setup(tmp_path)
    (root / 'Orders.vue').write_text('<template><button /></template>\n<script setup lang="ts">\nfunction submit() { normalize() }\nfunction normalize() { return 1 }\n</script>\n')
    with LearningStore(tmp_path / 'memory') as store:
        result = refresh_project(store, str(root))
        file = next(f for f in result['analysis']['files'] if f['path'] == 'Orders.vue')
        assert file['status'] == 'parsed'
        assert any(s['name'] == 'submit' and s['line'] == 3 for s in file['symbols'])


def test_refresh_preserves_revision_written_while_source_scan_runs(tmp_path, monkeypatch):
    root = setup(tmp_path)
    with LearningStore(tmp_path / 'memory') as store:
        initial = refresh_project(store, str(root))
        scan = analysis.scan
        def concurrent_note(*args, **kwargs):
            result = scan(*args, **kwargs)
            with LearningStore(tmp_path / 'memory') as other:
                add_note(other, str(root), 'architecture', 'Submission invokes normalization.', ['orders.py'])
            return result
        monkeypatch.setattr(analysis, 'scan', concurrent_note)
        result = refresh_project(store, str(root))
        assert result['revision'] == initial['revision'] + 1
        assert result['notes'][0]['content'] == 'Submission invokes normalization.'


def test_body_only_change_invalidates_an_already_delivered_conclusion(tmp_path):
    root = setup(tmp_path)
    with LearningStore(tmp_path / 'memory') as store:
        refresh_project(store, str(root))
        add_note(store, str(root), 'architecture', 'The stable function returns 1.', ['stable.py'])
        before = project_detail(store, str(root))
        query = 'Explain the project architecture stable function'
        assert 'returns 1' in store.context(query, str(root), 'same-session')['context']
        (root / 'stable.py').write_text('def stable():\n    return 2\n')
        after = refresh_project(store, str(root))
        assert after['revision'] > before['revision']
        context = store.context(query, str(root), 'same-session')['context']
        assert 'changed sources' in context
        assert 'returns 1' not in context
