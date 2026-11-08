"""Build twice, verify identical wheels, and exercise upgrade/rollback locally.

Run with the project's Python environment (dependencies are reused in isolation).
Nothing is published and live Cortex data is never opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import site
import subprocess
import sys
import tempfile
import tomllib
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / 'src/cortex_claude/web/frontend'


def command(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs)


def version() -> str:
    expected = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    assert json.loads((FRONTEND / 'package.json').read_text())['version'] == expected
    assert json.loads((FRONTEND / 'package-lock.json').read_text())['version'] == expected
    assert f'__version__ = "{expected}"' in (ROOT / 'src/cortex_claude/__init__.py').read_text()
    locked = tomllib.loads((ROOT / 'uv.lock').read_text())
    assert next(p['version'] for p in locked['package'] if p['name'] == 'cortex-claude') == expected
    return expected


def check_wheel(path: Path, expected: str) -> None:
    with zipfile.ZipFile(path) as wheel:
        names = set(wheel.namelist())
        assert not any('/frontend/' in name or name.startswith('videos/') for name in names)
        index = wheel.read('cortex_claude/web/static/index.html').decode()
        for asset in re.findall(r'(?:src|href)="(/assets/[^"?]+)', index):
            assert 'cortex_claude/web/static' + asset in names, asset
        assert f'__version__ = "{expected}"' in wheel.read('cortex_claude/__init__.py').decode()
        assert wheel.testzip() is None


def build(output: Path, offline: bool) -> dict:
    expected = version()
    output.mkdir(parents=True, exist_ok=True)
    hashes, wheels = [], []
    env = {**os.environ, 'SOURCE_DATE_EPOCH': '1704067200'}
    for index in range(2):
        command(['npm', 'run', 'build'], cwd=FRONTEND, env=env)
        destination = output / f'build-{index + 1}'
        command(['uv', 'build', '--wheel', '--out-dir', str(destination), *(['--offline'] if offline else [])], cwd=ROOT, env=env)
        wheel = destination / f'cortex_claude-{expected}-py3-none-any.whl'
        check_wheel(wheel, expected)
        hashes.append(hashlib.sha256(wheel.read_bytes()).hexdigest()); wheels.append(wheel)
    if hashes[0] != hashes[1]:
        raise ValueError('Independent builds differ; release was not verified')
    final = output / wheels[0].name
    final.write_bytes(wheels[0].read_bytes())
    result = {'version': expected, 'wheel': final.name, 'sha256': hashes[0], 'reproducible': True}
    (output / 'SHA256SUMS').write_text(f'{hashes[0]}  {final.name}\n')
    (output / 'build-report.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def rollback(current: Path, previous: Path, output: Path) -> dict:
    if not current.is_file() or not previous.is_file():
        raise ValueError('Both wheel files are required')
    with tempfile.TemporaryDirectory(prefix='cortex-upgrade-') as directory:
        root = Path(directory).resolve()
        environment = root / 'env'
        venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
        python = environment / 'bin/python'
        packages = next((environment / 'lib').glob('python*/site-packages'))
        # Reuse dependencies only; the actual Cortex distribution is installed
        # and replaced inside this disposable virtual environment.
        (packages / 'cortex-test-dependencies.pth').write_text(''.join(
            'import sys; sys.path.append(' + repr(path) + ')\n' for path in site.getsitepackages()))
        repo, home = root / 'repo', root / 'memory'
        repo.mkdir(); home.mkdir()
        (repo / 'package.json').write_text('{"name":"upgrade-fixture"}')
        (repo / 'subject.py').write_text('def preserved():\n    return 42\n')
        (home / 'config.json').write_text('{"learning":{"semantic_enabled":false}}')
        check = root / 'check.py'
        check.write_text('''import json,os,sys
from pathlib import Path
import cortex_claude
from cortex_claude.learning.store import LearningStore
from cortex_claude.learning.projects import refresh_project,add_note,project_detail
from cortex_claude.learning.tasks import save_task,list_tasks
assert Path(cortex_claude.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
home,repo=Path(sys.argv[1]),sys.argv[2]
with LearningStore(home) as store:
 if sys.argv[3]=='seed':
  refresh_project(store,repo)
  add_note(store,repo,'architecture','The preserved function returns 42.',['subject.py'])
  save_task(store,repo,'upgrade',title='Keep data',summary='Verified before upgrade',next_step='Check after downgrade')
 else:
  refresh_project(store,repo)
 assert project_detail(store,repo)['notes'][0]['content']=='The preserved function returns 42.'
 assert list_tasks(store,repo)[0]['summary']=='Verified before upgrade'
 assert store.conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 assert not store.conn.execute('PRAGMA foreign_key_check').fetchall()
 print(json.dumps({'version':cortex_claude.__version__,'notes':1,'checkpoints':1,'integrity':'ok'}))
''')
        stages = []
        for wheel, phase in [(previous, 'seed'), (current, 'upgrade'), (previous, 'rollback'), (current, 'upgrade-again')]:
            command(['uv', 'pip', 'install', '--python', str(python), '--no-deps', '--offline', '--reinstall-package', 'cortex-claude', str(wheel.resolve())])
            result = command([str(python), str(check), str(home), str(repo), phase], cwd=root,
                             env={**os.environ, 'CORTEX_HOME': str(home)})
            stages.append({'phase': phase, **json.loads(result.stdout)})
    report = {'passed': True, 'scope': 'disposable-virtualenv-and-database', 'stages': stages,
              'current_sha256': hashlib.sha256(current.read_bytes()).hexdigest(),
              'previous_sha256': hashlib.sha256(previous.read_bytes()).hexdigest()}
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    package = commands.add_parser('build'); package.add_argument('--output', type=Path, required=True); package.add_argument('--offline', action='store_true')
    check = commands.add_parser('rollback'); check.add_argument('--current', type=Path, required=True); check.add_argument('--previous', type=Path, required=True); check.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    if options.action == 'build':
        result = build(options.output.resolve(), options.offline)
    else:
        result = rollback(options.current, options.previous, options.output)
    print(json.dumps(result, indent=2))
