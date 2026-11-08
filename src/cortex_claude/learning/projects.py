"""Evidence-backed project knowledge in the shared store, without tool transcripts.

The scanner reads bounded manifests/docs and describes only declared structure.
The working assistant supplies architectural synthesis through sourced notes.
Nothing from package scripts, documentation or repository configuration is run.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from cortex_claude.core.privacy import strip_private
from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.learning.extraction import terms
from cortex_claude.learning.policy import changed, snapshot

if TYPE_CHECKING:
    from cortex_claude.learning.store import LearningStore

_IGNORE = {".git", ".venv", "venv", "node_modules", "dist", "build", "target", "vendor", "coverage", "__pycache__", ".next", ".nuxt", ".output", ".cache", ".cortex-claude", "test-results", ".vitepress"}
_MANIFESTS = {"package.json", "pyproject.toml", "go.mod", "Cargo.toml"}
_STACK = {"vue": "Vue", "react": "React", "next": "Next.js", "nuxt": "Nuxt", "@nestjs/core": "NestJS", "express": "Express", "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "mcp": "MCP", "@getcortexlabs/mavis-web": "Mavis Web", "typescript": "TypeScript", "vite": "Vite", "pytest": "pytest", "vitest": "Vitest", "@playwright/test": "Playwright", "prisma": "Prisma", "typeorm": "TypeORM", "sqlalchemy": "SQLAlchemy", "sqlite-vec": "SQLite vectors"}
_SENSITIVE = re.compile(r"(?:password|secret|api[_-]?key|access[_-]?token|auth[_-]?token|authorization)\s*[:=]", re.I)


def _text(value: object, limit: int = 180) -> str:
    if not isinstance(value, str) or _SENSITIVE.search(value):
        return ""
    return " ".join(strip_private(value).split())[:limit]


def _read(root: Path, relative: str) -> tuple[str, str] | None:
    path = root / relative
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            return None
        with path.open("rb") as stream:
            data = stream.read(200_001)
        if len(data) > 200_000 or b"\x00" in data:
            return None
        return data.decode("utf-8"), hashlib.sha256(data).hexdigest()
    except (OSError, UnicodeError):
        return None


def inspect_project(cwd: str) -> tuple[str, dict, dict]:
    from cortex_claude.learning.store import context_origin
    root = Path(context_origin(cwd)).resolve()
    if not root.is_dir() or not ((root / ".git").exists() or any((root / name).is_file() for name in _MANIFESTS)):
        raise ValueError("Open a project with a Git root or a supported package manifest")
    manifests, docs, inventory = [], [], []
    truncated = False
    directories = 0
    for folder, dirs, files in os.walk(root, followlinks=False):
        relative_dir = Path(folder).relative_to(root)
        directories += 1
        dirs[:] = sorted(d for d in dirs if d not in _IGNORE and not d.startswith('.') and not (Path(folder) / d).is_symlink()) if len(relative_dir.parts) < 5 else []
        for name in sorted(files):
            relative = (relative_dir / name).as_posix()
            if name in _MANIFESTS and len(manifests) < 24:
                manifests.append(relative)
            if name.lower() in {"readme.md", "architecture.md", "contributing.md", "agents.md"} and len(docs) < 12:
                docs.append(relative)
            if not name.startswith('.') and len(inventory) < 2000:
                inventory.append(relative)
        if directories >= 200 or len(inventory) >= 2000:
            truncated = True
            break
    # Root manifests first, then deterministic shallow module manifests.
    manifests.sort(key=lambda path: (path.count('/'), path))
    modules, sources, warnings = [], {}, []
    consumed = 0
    for path in manifests:
        loaded = _read(root, path)
        if not loaded:
            warnings.append(f"Could not read {path}")
            continue
        raw, digest = loaded
        if consumed + len(raw.encode()) > 600_000:
            truncated = True
            break
        consumed += len(raw.encode())
        source = {"path": path, "line": 1}
        module = {"name": Path(path).parent.name if '/' in path else root.name, "path": str(Path(path).parent), "manifest": path, "purpose": "", "stack": [], "commands": [], "entrypoints": [], "source": source}
        try:
            if path.endswith("package.json"):
                package = json.loads(raw)
                if not isinstance(package, dict):
                    raise ValueError("Manifest must be an object")
                module["name"] = _text(package.get("name"), 100) or module["name"]
                module["purpose"] = _text(package.get("description"), 250)
                dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
                module["stack"] = ["JavaScript/Node.js", *sorted({_STACK[name] for name in dependencies if name in _STACK})]
                manager = (_text(package.get("packageManager")) or "npm").split('@')[0]
                if manager not in {"npm", "pnpm", "yarn", "bun"}:
                    manager = "npm"
                scripts = package.get("scripts", {})
                if isinstance(scripts, dict):
                    for name, command in scripts.items():
                        if name in {"dev", "start", "build", "test", "test:unit", "test:e2e", "test:browser", "lint", "typecheck", "check", "docs:dev"} and _text(command):
                            module["commands"].append({"name": name, "command": f"{manager} run {name}", "definition": _text(command, 240), "cwd": module["path"], "source": source})
                for key in ("main", "module"):
                    if value := _text(package.get(key)):
                        module["entrypoints"].append(value)
            elif path.endswith("pyproject.toml"):
                package = tomllib.loads(raw)
                project = package.get("project", {})
                module["name"] = _text(project.get("name"), 100) or module["name"]
                module["purpose"] = _text(project.get("description"), 250)
                names = {re.split(r"[\s\[<>=!~;]", dependency)[0].lower() for dependency in project.get("dependencies", []) if isinstance(dependency, str)}
                module["stack"] = ["Python", *sorted({_STACK[name] for name in names if name in _STACK})]
                module["entrypoints"] = [f"{_text(key)} → {_text(value)}" for key, value in list(project.get("scripts", {}).items())[:8]]
                if "pytest" in package.get("tool", {}):
                    module["commands"].append({"name": "test", "command": "python -m pytest", "definition": "pytest configured in pyproject.toml", "cwd": module["path"], "source": source})
            elif path.endswith("Cargo.toml"):
                package = tomllib.loads(raw).get("package", {})
                module["name"] = _text(package.get("name"), 100) or module["name"]
                module["purpose"] = _text(package.get("description"), 250)
                module["stack"] = ["Rust"]
            else:
                match = re.search(r"^module\s+(\S+)", raw, re.M)
                module["name"] = _text(match[1], 100) if match else root.name
                module["stack"] = ["Go"]
        except (ValueError, TypeError, AttributeError):
            warnings.append(f"Invalid manifest: {path}")
            continue
        sources[path] = digest
        modules.append(module)
    documents = []
    for path in sorted(docs, key=lambda path: (path.count('/'), path)):
        loaded = _read(root, path)
        if not loaded or consumed + len(loaded[0].encode()) > 800_000:
            continue
        raw, digest = loaded
        consumed += len(raw.encode())
        sources[path] = digest
        from cortex_claude.learning.reading import redact_lines
        headings = [{"title": _text(line.lstrip('#').strip(), 100), "line": index} for index, line in enumerate(redact_lines(raw).splitlines(), 1) if re.match(r"^#{1,3}\s+", line)][:8]
        documents.append({"path": path, "headings": headings})
    primary = next((m for m in modules if m["path"] == "." and m["purpose"]), modules[0] if modules else None)
    # Paths are navigational evidence, not claims about business behavior.
    important = [p for p in inventory if re.search(r"(?:^|/)(?:src|app|apps|packages|server|api|tests|test|scripts|docs)(?:/|$)", p) and p.count('/') <= 2][:20]
    data = {"name": primary["name"] if primary else root.name, "purpose": primary["purpose"] if primary else "", "modules": modules, "documents": documents, "structure": important, "warnings": warnings, "truncated": truncated, "basis": "declared-files"}
    return str(root), data, sources


def refresh_project(store: LearningStore, cwd: str) -> dict:
    if not store.config.enabled or not store.config.project_memory:
        return {"status": "disabled"}
    from cortex_claude.learning.analysis import inventory, scan, stamp
    from cortex_claude.learning.store import context_origin
    origin = context_origin(cwd)
    root = Path(origin)
    if not root.is_dir():
        raise ValueError('Project directory does not exist')
    paths, partial = inventory(root)
    declared = [p for p in paths if Path(p).name in _MANIFESTS or Path(p).name.lower() in {'readme.md', 'architecture.md', 'contributing.md', 'agents.md'}]
    stamps = {}
    for path in declared:
        try:
            stamps[path] = stamp(root / path)
        except OSError:
            pass
    old = store.conn.execute("SELECT data,sources,revision FROM project_profiles WHERE origin=?", (origin,)).fetchone()
    previous = json.loads(old['data']) if old else {}
    if old and previous.get('declaration_stamps') == stamps:
        data, sources = previous, json.loads(old['sources'])
    else:
        origin, data, sources = inspect_project(cwd)
    data['declaration_stamps'] = stamps
    data['analysis'] = scan(store, origin, paths, partial)
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True)
    def semantic(value):
        value = {k: v for k, v in value.items() if k != 'declaration_stamps'}
        if 'analysis' in value:
            value['analysis'] = {k: v for k, v in value['analysis'].items() if k != 'scan'}
        return value
    with store.conn:
        store.conn.execute('BEGIN IMMEDIATE')
        old = store.conn.execute("SELECT data,sources,revision FROM project_profiles WHERE origin=?", (origin,)).fetchone()
        code_changed = bool(data['analysis']['scan']['changed'] or data['analysis']['scan']['removed'])
        revision = old["revision"] if old and not code_changed and semantic(json.loads(old['data'])) == semantic(data) and json.loads(old["sources"]) == sources else (old["revision"] + 1 if old else 1)
        store.conn.execute("INSERT INTO project_profiles VALUES (?,?,?,?,?,?) ON CONFLICT(origin) DO UPDATE SET name=excluded.name,data=excluded.data,sources=excluded.sources,revision=excluded.revision,updated_at=excluded.updated_at", (origin, data["name"], encoded, json.dumps(sources), revision, time.time()))
    return project_detail(store, origin) or {}


def _fresh(origin: str, sources: dict) -> bool:
    root = Path(origin)
    return all((loaded := _read(root, path)) is not None and loaded[1] == digest for path, digest in sources.items())


def project_detail(store: LearningStore, cwd: str) -> dict | None:
    from cortex_claude.learning.store import context_origin
    row = store.conn.execute("SELECT * FROM project_profiles WHERE origin=?", (context_origin(cwd),)).fetchone()
    if not row:
        return None
    result = {**json.loads(row["data"]), "origin": row["origin"], "revision": row["revision"], "updated_at": row["updated_at"], "needs_review": not _fresh(row["origin"], json.loads(row["sources"]))}
    result["notes"] = [{**dict(note), "sources": list(json.loads(note["sources"])), "needs_review": changed(row["origin"], json.loads(note["sources"]))} for note in store.conn.execute("SELECT * FROM project_notes WHERE origin=? ORDER BY updated_at DESC", (row["origin"],))]
    from cortex_claude.learning.analysis import outdated
    result.pop('declaration_stamps', None)
    result['changed_files'] = outdated(store, row['origin'])
    result['review_queue'] = [{'id': note['id'], 'section': note['section'], 'sources': note['sources'],
        'reason': 'source-changed-or-missing'} for note in result['notes'] if note['needs_review']]
    if result['changed_files']:
        result['needs_review'] = True
        # Never serve stale static paths/calls as current architecture evidence.
        if 'analysis' in result:
            bad = set(result['changed_files'])
            result['analysis']['files'] = [f for f in result['analysis']['files'] if f['path'] not in bad]
            result['analysis']['flows'] = [f for f in result['analysis']['flows'] if f['path'] not in bad]
    return result


def list_projects(store: LearningStore) -> list[dict]:
    return [value for row in store.conn.execute("SELECT origin FROM project_profiles ORDER BY updated_at DESC LIMIT 100") if (value := project_detail(store, row[0]))]


def add_note(store: LearningStore, cwd: str, section: str, content: str, sources: list[str]) -> dict:
    from cortex_claude.learning.store import context_origin
    if not store.config.enabled or not store.config.project_memory:
        return {"status": "disabled"}
    if section not in {"purpose", "architecture", "conventions", "decisions"}:
        raise ValueError("Use purpose, architecture, conventions or decisions")
    content = _text(content, 2000)
    if not content or count_tokens(content) > 160 or re.match(r"^(?:Command:|Bash:|Read file:)", content, re.I):
        raise ValueError("Write a meaningful conclusion within 160 tokens, not a tool transcript")
    if not sources or len(sources) > 5:
        raise ValueError("Cite 1–5 relative source files that support this conclusion")
    origin = context_origin(cwd)
    fingerprints = snapshot(origin, sources)
    if any(any(part in _IGNORE or part.startswith('.') for part in Path(path).parts) or Path(path).name.lower().endswith(('.pem', '.key', '.p12')) for path in fingerprints):
        raise ValueError("Do not cite private, generated or hidden files")
    if not store.conn.execute("SELECT 1 FROM project_profiles WHERE origin=?", (origin,)).fetchone():
        refresh_project(store, cwd)
    note_id = 'project-note:' + hashlib.sha256(f"{origin}:{section}:{content}".encode()).hexdigest()[:16]
    with store.conn:
        existing = store.conn.execute("SELECT sources FROM project_notes WHERE id=?", (note_id,)).fetchone()
        count = store.conn.execute("SELECT COUNT(*) FROM project_notes WHERE origin=?", (origin,)).fetchone()[0]
        if not existing and count >= 20:
            raise ValueError("Keep at most 20 project conclusions; remove obsolete notes first")
        store.conn.execute("INSERT INTO project_notes VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET sources=excluded.sources,updated_at=excluded.updated_at", (note_id, origin, section, content, json.dumps(fingerprints), time.time()))
        if not existing or json.loads(existing[0]) != fingerprints:
            store.conn.execute("UPDATE project_profiles SET revision=revision+1 WHERE origin=?", (origin,))
    return {"id": note_id, "section": section, "source": "assistant-synthesis", "evidence_files": list(fingerprints)}


def project_context(store: LearningStore, query: str, cwd: str, sid: str | None) -> dict | None:
    if not store.config.project_memory:
        return None
    data = project_detail(store, cwd)
    if not data or data["needs_review"]:
        return None
    if sid and store.conn.execute("SELECT 1 FROM project_deliveries WHERE session_id=? AND origin=? AND revision=?", (sid, data["origin"], data["revision"])).fetchone():
        return None
    cues = terms(query)
    relevant = cues & (terms(data["name"] + ' ' + data["purpose"]) | {'code', 'project', 'projeto', 'repository', 'repositorio', 'test', 'build', 'architecture', 'api', 'frontend', 'backend', 'bug', 'stack', 'implement', 'deploy'})
    if not relevant:
        return None
    line = '- Project ' + data['name'] + ' (details and sources: cortex_project read).'
    if data.get('review_queue'):
        line += f" {len(data['review_queue'])} prior conclusions have changed sources; re-read before using them."
    for note in sorted(data["notes"], key=lambda n: len(cues & terms(n["content"])), reverse=True):
        if not note["needs_review"] and cues & terms(note["content"]):
            # Prefer an actual conclusion to a longer inventory. Use complete
            # sentences and keep the full source trail in the bounded read tool.
            sentences = re.split(r'(?<=[.!?])\s+', note['content'])
            added = False
            for sentence in sentences:
                proposal = line + (' ' + note['section'] + ': ' if not added else ' ') + sentence
                if count_tokens(proposal) > 115:
                    break
                line, added = proposal, True
            if added:
                break
    for module in data["modules"][:3]:
        proposal = line + f" Declared {module['path']}: {', '.join(module['stack'][:4])}."
        if count_tokens(proposal) <= 115:
            line = proposal
        for command in module["commands"]:
            if terms(command["name"]) & cues:
                proposal = line + f" {command['command']} (cwd {command['cwd']}; declared, not executed)."
                if count_tokens(proposal) <= 115:
                    line = proposal
                break
    return {"origin": data["origin"], "revision": data["revision"], "line": line}


def read_project(store: LearningStore, cwd: str, max_tokens: int = 800) -> dict:
    if not 120 <= max_tokens <= 2000:
        raise ValueError("max_tokens must be between 120 and 2000")
    data = project_detail(store, cwd)
    if not data:
        return {"status": "not-indexed", "next": "cortex_project refresh"}
    result = {key: data[key] for key in ("name", "origin", "purpose", "needs_review", "revision")}
    result.update({"modules": [], "notes": [], "documents": [], "flows": [], "more": False})
    if 'analysis' in data:
        result['coverage'] = {k: data['analysis']['coverage'][k] for k in ('analyzed', 'discovered', 'partial')}
    if data.get('review_queue'):
        result['pending_reviews'] = len(data['review_queue'])
    if not any(n['section'] == 'architecture' and not n['needs_review'] for n in data['notes']):
        result['next'] = 'Read relevant docs and entrypoints; record supported architecture/conventions with cortex_project note. Manifest facts alone are not a complete architecture analysis.'
    for category in ("notes", "modules", "flows", "documents"):
        for item in (data.get('analysis', {}).get('flows', []) if category == 'flows' else data[category]):
            proposal = {**result, category: [*result[category], item]}
            if count_tokens(json.dumps(proposal, ensure_ascii=False)) <= max_tokens:
                result = proposal
            else:
                result["more"] = True
    if count_tokens(json.dumps(result, ensure_ascii=False)) > max_tokens:
        return {"status": "budget-too-small", "next": "Increase max_tokens"}
    return result
