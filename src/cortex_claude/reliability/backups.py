"""Verified online SQLite backups and staged restoration; never overwrite live data."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path

import sqlite_vec

from cortex_claude.reliability.config import RecoveryConfig
from cortex_claude.reliability.files import atomic_write, lock, read_json, state, write_json


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def check_database(path: Path) -> dict:
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)) as conn:
        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
        check = conn.execute('PRAGMA integrity_check').fetchall()
        if check != [('ok',)] or conn.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError(f'Database integrity failure: {path.name}')
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        tables = {'lessons', 'project_profiles', 'project_notes', 'work_items', 'memories', 'execution_history'} & names
        return {table: conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in sorted(tables)}


def validate(directory: Path) -> dict:
    directory = directory.resolve()
    manifest = read_json(directory / 'manifest.json')
    if manifest.get('format') != 1 or not isinstance(manifest.get('files'), dict) or not manifest['files']:
        raise ValueError('Invalid or incomplete backup')
    for relative, record in manifest['files'].items():
        candidate = directory / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts or candidate.is_symlink() or not candidate.resolve().is_relative_to(directory):
            raise ValueError('Unsafe path in backup')
        if not candidate.is_file() or candidate.stat().st_size != record['size'] or digest(candidate) != record['sha256']:
            raise ValueError(f'Backup checksum mismatch: {relative}')
        if candidate.suffix == '.db':
            if check_database(candidate) != record.get('tables'):
                raise ValueError(f'Backup table verification failed: {relative}')
    return manifest


def snapshots(home: Path) -> list[dict]:
    items = []
    for directory in (home / 'backups').glob('snapshot-*'):
        if directory.is_symlink():
            continue
        try:
            value = read_json(directory / 'manifest.json')
            if value.get('format') == 1 and value.get('verified_at'):
                items.append({'id': directory.name, 'created_at': value['created_at'], 'verified_at': value['verified_at'],
                              'size': sum(item['size'] for item in value['files'].values()), 'files': len(value['files']),
                              'tables': {path: item.get('tables') for path, item in value['files'].items() if path.endswith('.db')}})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(items, key=lambda item: item['created_at'], reverse=True)


def _copy_database(source: Path, destination: Path) -> dict:
    deadline = time.monotonic() + 90
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError('Database backup timed out')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=3)) as reader, closing(sqlite3.connect(destination)) as writer:
        reader.backup(writer, pages=256, progress=progress, sleep=.01)
    return check_database(destination)


def create(home: Path, *, reason: str = 'manual') -> dict:
    home = home.resolve()
    config = RecoveryConfig.load(home)
    root = home / 'backups'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock(home / 'recovery' / 'backup.lock', blocking=False):
        staged = Path(tempfile.mkdtemp(prefix='.snapshot-', dir=root))
        try:
            files = {}
            with lock(home / 'recovery' / 'worker.lock'):
                paths = [home / 'learning.db', home / 'global.db', *sorted((home / 'scopes').glob('*.db'))]
                for source in paths:
                    if not source.is_file():
                        continue
                    if source.is_symlink():
                        raise ValueError('Backup refuses linked database files')
                    relative = str(source.relative_to(home))
                    target = staged / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    tables = _copy_database(source, target)
                    files[relative] = {'size': target.stat().st_size, 'sha256': digest(target), 'tables': tables}
                # Pending operations are part of recovery, not searchable memory.
                for source in [home / 'config.json', *(home / 'recovery' / 'pending').glob('*.json')]:
                    if not source.is_file() or source.is_symlink():
                        continue
                    relative = str(source.relative_to(home))
                    target = staged / relative
                    # Preserve even a damaged pending record for recovery;
                    # its JSON validity must not prevent backing up the DBs.
                    atomic_write(target, source.read_bytes())
                    files[relative] = {'size': target.stat().st_size, 'sha256': digest(target)}
            if not any(name.endswith('.db') for name in files):
                raise ValueError('No Cortex database exists to back up')
            now = time.time()
            ident = time.strftime('snapshot-%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
            manifest = {'format': 1, 'id': ident, 'reason': reason, 'created_at': now, 'verified_at': now, 'files': files}
            write_json(staged / 'manifest.json', manifest)
            validate(staged)
            # All staged files, including SQLite backup outputs, reach disk
            # before the manifest directory is published as a complete backup.
            for path in staged.rglob('*'):
                if path.is_file():
                    with path.open('rb') as stream:
                        os.fsync(stream.fileno())
            destination = root / ident
            staged.rename(destination)
            fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            state(home, last_backup_at=now, last_backup_id=ident, backup_error=None)
            if config.mirror_directory:
                mirror = Path(config.mirror_directory).expanduser().resolve()
                if mirror == home or mirror.is_relative_to(home):
                    raise ValueError('Mirror must be outside the Cortex data directory')
                if not mirror.is_dir():
                    raise ValueError('Configured backup mirror is unavailable')
                mirror_stage = mirror / ('.' + ident)
                shutil.copytree(destination, mirror_stage)
                validate(mirror_stage)
                mirror_stage.rename(mirror / ident)
                state(home, last_mirror_at=time.time(), mirror_error=None)
            for old in snapshots(home)[config.backup_keep:]:
                shutil.rmtree(root / old['id'])
            return {'id': ident, 'verified': True, 'files': len(files), 'size': sum(item['size'] for item in files.values())}
        except Exception as error:
            state(home, backup_error={'type': type(error).__name__, 'at': time.time()})
            raise
        finally:
            if staged.exists():
                shutil.rmtree(staged)


def resolve(home: Path, ident: str) -> Path:
    if not ident.startswith('snapshot-') or Path(ident).name != ident:
        raise ValueError('Choose a snapshot identifier from backup list')
    path = home / 'backups' / ident
    if path.is_symlink() or not path.is_dir():
        raise ValueError('Backup not found')
    return path


def restore(home: Path, ident: str, destination: Path) -> dict:
    source = resolve(home, ident)
    manifest = validate(source)
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Restore destination must not exist; live data is never overwritten')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix='.cortex-restore-', dir=destination.parent))
    try:
        for relative in manifest['files']:
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)
            if digest(target) != manifest['files'][relative]['sha256']:
                raise ValueError('Restored file checksum mismatch')
            if target.suffix == '.db':
                check_database(target)
            with target.open('rb') as stream:
                os.fsync(stream.fileno())
        if destination.exists():
            raise ValueError('Restore destination appeared during restoration')
        staged.rename(destination)
        fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        state(home, last_restore_test_at=time.time(), restore_error=None)
        return {'restored': True, 'destination': str(destination), 'backup': ident, 'files': len(manifest['files'])}
    finally:
        if staged.exists():
            shutil.rmtree(staged)


def test_restore(home: Path, ident: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='cortex-restore-check-') as directory:
        result = restore(home, ident, Path(directory) / 'restored')
    return {'verified': True, 'backup': ident, 'files': result['files']}


def due(home: Path) -> bool:
    config = RecoveryConfig.load(home)
    current = read_json(home / 'recovery' / 'state.json')
    return config.auto_backup and time.time() - current.get('last_backup_at', 0) >= config.backup_interval_hours * 3600
