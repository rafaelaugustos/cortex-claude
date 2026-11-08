"""Incremental static evidence. Symbols and calls are not business assertions."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path

from cortex_claude.code.extractor import EXTENSION_TO_LANGUAGE, extract_symbols, _get_parser
from cortex_claude.learning.reading import redact_lines

MAX_FILES, MAX_BYTES = 240, 2_000_000
FORMAT = 1
SUPPORTED = {**EXTENSION_TO_LANGUAGE, '.vue': 'vue'}


def stamp(path: Path) -> str:
    info = path.stat()
    return f'{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}'


def inventory(root: Path) -> tuple[list[str], bool]:
    from cortex_claude.learning.projects import _IGNORE
    paths = []
    folders = 0
    for folder, directories, files in os.walk(root, followlinks=False):
        folders += 1
        relative = Path(folder).relative_to(root)
        directories[:] = sorted(d for d in directories if d not in _IGNORE and not d.startswith('.')
            and not (Path(folder) / d).is_symlink()) if len(relative.parts) < 8 else []
        for name in sorted(files):
            path = Path(folder) / name
            if not name.startswith('.') and not path.is_symlink() and path.is_file():
                paths.append(path.relative_to(root).as_posix())
            if len(paths) >= 4000:
                return paths, True
        if folders >= 400:
            return paths, True
    return paths, False


def _symbols(path: str, text: str) -> tuple[list[dict], str]:
    language = SUPPORTED[Path(path).suffix.lower()]
    if language == 'vue':
        symbols, status = [], 'parsed'
        for match in re.finditer(r'<script\b([^>]*)>([\s\S]*?)</script\s*>', text, re.I):
            extension = '.ts' if re.search(r'\blang\s*=\s*[\"\x27]ts[\"\x27]', match[1]) else '.js'
            found, state = _symbols(path + extension, match[2])
            offset = text[:match.start(2)].count('\n')
            symbols.extend({**symbol, 'line': symbol['line'] + offset} for symbol in found)
            if state != 'parsed':
                status = state
        return symbols[:60], status
    if language == 'python':
        # Built-in parser keeps Python analysis available without optional extras.
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return [], 'parse-error'
        imports = sorted({n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
                         | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names})[:16]
        symbols = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                calls = sorted({n.func.id if isinstance(n.func, ast.Name) else n.func.attr for n in ast.walk(node)
                    if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))})[:16]
                symbols.append({'name': node.name, 'kind': 'class' if isinstance(node, ast.ClassDef) else 'function',
                                'line': node.lineno, 'calls': calls, 'imports': imports})
        return sorted(symbols, key=lambda s: s['line'])[:60], 'parsed'
    if _get_parser(language) is None:
        return [], 'parser-unavailable'
    try:
        symbols = extract_symbols(path, text)
        return [{'name': s.name, 'kind': s.kind, 'line': s.line, 'calls': s.calls[:16], 'imports': s.imports[:16]}
                for s in symbols[:60]], 'parsed'
    except (ValueError, TypeError, RuntimeError):
        return [], 'parse-error'


def scan(store, origin: str, paths: list[str], partial: bool = False) -> dict:
    root = Path(origin)
    store.conn.execute('CREATE TABLE IF NOT EXISTS project_code_cache (origin TEXT NOT NULL, path TEXT NOT NULL, stamp TEXT NOT NULL, digest TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(origin,path))')
    old = {r['path']: dict(r) for r in store.conn.execute('SELECT * FROM project_code_cache WHERE origin=?', (origin,))}
    candidates = sorted(p for p in paths if Path(p).suffix.lower() in SUPPORTED and not p.endswith(('.min.js', '.d.ts')))
    # Entry points and application code precede tests and scripts when bounded.
    candidates.sort(key=lambda p: (p.startswith(('tests/', 'test/', 'scripts/')), p.count('/'), p))
    selected = candidates[:MAX_FILES]
    files, changed, removed, unavailable = [], [], [], []
    read_bytes = reused = 0
    with store.conn:
        for path in selected:
            absolute = root / path
            try:
                if absolute.is_symlink() or not absolute.resolve().is_relative_to(root):
                    raise ValueError('Unsafe source')
                current = stamp(absolute)
                cached = old.get(path)
                if cached and cached['stamp'] == current and json.loads(cached['data']).get('format') == FORMAT and json.loads(cached['data']).get('status') != 'parser-unavailable':
                    files.append(json.loads(cached['data'])); reused += 1
                    continue
                size = absolute.stat().st_size
                if size > 200_000 or read_bytes + size > MAX_BYTES:
                    unavailable.append(path); continue
                with absolute.open('rb') as stream:
                    raw = stream.read(200_001)
                if len(raw) > 200_000 or b'\x00' in raw:
                    unavailable.append(path); continue
                read_bytes += len(raw)
                digest = hashlib.sha256(raw).hexdigest()
                if cached and cached['digest'] == digest and json.loads(cached['data']).get('format') == FORMAT and json.loads(cached['data']).get('status') != 'parser-unavailable':
                    data = json.loads(cached['data'])
                else:
                    symbols, status = _symbols(path, redact_lines(raw.decode('utf-8')))
                    data = {'path': path, 'symbols': symbols, 'status': status, 'format': FORMAT}
                    changed.append(path)
                store.conn.execute('INSERT OR REPLACE INTO project_code_cache VALUES (?,?,?,?,?)',
                    (origin, path, current, digest, json.dumps(data, ensure_ascii=False)))
                files.append(data)
            except (OSError, ValueError, UnicodeError):
                unavailable.append(path)
        # Never keep evidence for deleted, inaccessible, or now-excluded files.
        retained = {f['path'] for f in files}
        for path in old.keys() - retained:
            store.conn.execute('DELETE FROM project_code_cache WHERE origin=? AND path=?', (origin, path))
            removed.append(path)
    flows = []
    for file in files:
        definitions = {}
        for symbol in file['symbols']:
            definitions.setdefault(symbol['name'], []).append(symbol)
        for symbol in file['symbols']:
            if symbol['kind'] != 'function':
                continue
            for callee in symbol['calls']:
                target = definitions.get(callee, [])
                flows.append({'caller': symbol['name'], 'callee': callee, 'path': file['path'], 'line': symbol['line'],
                              'resolution': 'same-file-candidate' if len(target) == 1 else 'unresolved'})
    return {'basis': 'static-code', 'files': files, 'flows': flows[:120],
            'coverage': {'discovered': len(candidates), 'analyzed': sum(f['status'] == 'parsed' for f in files), 'partial': partial or len(candidates) > MAX_FILES or bool(unavailable) or any(f['status'] != 'parsed' for f in files),
                         'unavailable': unavailable[:40], 'parser_unavailable': sum(f['status'] == 'parser-unavailable' for f in files)},
            'scan': {'read_files': len(files) - reused, 'reused_files': reused, 'read_bytes': read_bytes,
                     'changed': changed, 'removed': sorted(removed)}}


def outdated(store, origin: str) -> list[str]:
    # Used by the dashboard; no file contents are read for unchanged metadata.
    if not store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='project_code_cache'").fetchone():
        return []
    result = []
    root = Path(origin)
    for row in store.conn.execute('SELECT path,stamp FROM project_code_cache WHERE origin=?', (origin,)):
        path = root / row['path']
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(root) or stamp(path) != row['stamp']:
                result.append(row['path'])
        except OSError:
            result.append(row['path'])
    return result
