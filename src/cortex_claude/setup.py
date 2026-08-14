from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / ".cortex-claude")))
CLAUDE_CONFIG = Path.home() / ".claude.json"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
HOOKS_DIR = CORTEX_HOME / "hooks"

CLAUDE_MD_CONTENT = """# Cortex Memory

You have access to **Cortex**, a persistent memory system with a knowledge graph and code graph. Use it.

## Rules

1. **Before reading a code file to find a function** — try `cortex_code(symbol)` first. Returns where it's defined, what it calls, who calls it, and which memories mention it. ~50-150 tokens vs ~1000+ to read the file.
2. **Before saying "I don't know"** — always check Cortex first with `cortex_recall` or `cortex_facts`.
3. **Save important context** — when you learn something significant about the project, user preferences, architecture decisions, or bugs, save it with `cortex_save`.
4. **Use facts for quick lookups** — `cortex_facts` returns structured triplets at minimal token cost. Use it for "what does X use?" type questions.
5. **Use traverse for exploration** — `cortex_traverse` follows entity connections. Use it to discover related information you didn't know to ask about. Accepts `start="cluster:42"` to begin from a sub-graph.
6. **Use clusters for top-down navigation** — `cortex_clusters` lists semantic sub-graphs of your memory so you can see what topics exist before drilling in.
7. **Respect privacy** — never save content wrapped in `<private>...</private>` tags. Cortex strips these automatically, but be mindful of sensitive data.

## Available Tools

| Tool | When to use |
|------|------------|
| `cortex_code` | Look up a code symbol: definition, callers, callees, mentions. Cheap alternative to reading a file. |
| `cortex_index_code` | Index a file or directory into the code graph (Python, JS/TS, Go, Java, Swift, Kotlin). |
| `cortex_save` | Save information worth remembering across sessions |
| `cortex_recall` | Search memories by meaning (semantic + keyword) |
| `cortex_facts` | Quick structured lookup from knowledge graph |
| `cortex_traverse` | Explore connections: start from entity or `cluster:<id>` |
| `cortex_clusters` | List or rebuild sub-graphs of memory (auto-formed by similarity) |
| `cortex_forget` | Delete outdated or wrong memories (dry-run first) |
| `cortex_scopes` | Manage memory scopes (list, create, link) |
| `cortex_status` | Check memory stats (count, size, scopes) |

## What to Save

- Architecture decisions and their rationale
- User preferences and conventions
- Bug context and root causes
- Project-specific terminology
- Environment and deployment details
- API contracts and integrations

## What NOT to Save

- Code that's already in files (it's in the repo — use `cortex_code` instead)
- Temporary debugging output
- Content marked with `<private>` tags
- Information that changes every commit (use git for that)
"""

SESSION_START_HOOK = '''#!/bin/bash
CORTEX_HOME="${CORTEX_HOME:-$HOME/.cortex-claude}"
GLOBAL_DB="$CORTEX_HOME/global.db"
SOCKET="$CORTEX_HOME/cortex.sock"

INPUT=$(cat)

if [ ! -S "$SOCKET" ]; then
  python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from cortex_claude.daemon import ensure_running
    ensure_running()
except Exception:
    pass
" 2>/dev/null &
fi

# Fire-and-forget: ask the daemon to index the whole project into the code
# graph if it hasn't been indexed yet (see CortexDaemon._maybe_index_project).
# Doesn't block session start — no response is read back.
(echo "$INPUT" | python3 -c "
import json, socket, sys, os

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

cwd = data.get('cwd')
if not cwd:
    sys.exit(0)

sock_path = os.path.expanduser('$SOCKET')
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(sock_path)
    s.sendall(json.dumps({'action': 'index_project', 'cwd': cwd}).encode())
    s.shutdown(socket.SHUT_WR)
    s.close()
except Exception:
    pass
" 2>/dev/null) &

[ ! -f "$GLOBAL_DB" ] && exit 0

CONTEXT=$(python3 -c "
import sqlite3, os, glob

cortex_home = os.path.expanduser('${CORTEX_HOME:-~/.cortex-claude}')
dbs = []

global_db = os.path.join(cortex_home, 'global.db')
if os.path.exists(global_db):
    dbs.append(('global', global_db))

scopes_dir = os.path.join(cortex_home, 'scopes')
if os.path.isdir(scopes_dir):
    for f in glob.glob(os.path.join(scopes_dir, '*.db')):
        name = os.path.basename(f).replace('.db','').replace('__',':')
        dbs.append((name, f))

if not dbs:
    exit(0)

total_memories = 0
total_facts = 0
recent_facts = []

for scope_name, db_path in dbs:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT COUNT(*) as c FROM memories').fetchone()
        total_memories += row[0]
        row = conn.execute('SELECT COUNT(*) as c FROM facts').fetchone()
        total_facts += row[0]
        rows = conn.execute(
            'SELECT subject, relation, object FROM facts ORDER BY confidence DESC, created_at DESC LIMIT 15'
        ).fetchall()
        for r in rows:
            recent_facts.append(f'{r[0]} -> {r[1]} -> {r[2]}')
        conn.close()
    except Exception:
        pass

if total_memories == 0:
    exit(0)

lines = [
    'You have access to Cortex persistent memory (cortex_save, cortex_recall, cortex_facts, cortex_traverse, cortex_forget, cortex_scopes, cortex_status).',
    'IMPORTANT: Always use cortex_recall or cortex_facts BEFORE saying you do not know something.',
    f'Memory: {total_memories} memories, {total_facts} facts, {len(dbs)} scope(s).',
]

if recent_facts:
    lines.append('')
    lines.append('Known facts:')
    for f in recent_facts[:10]:
        lines.append(f'  {f}')

print(chr(10).join(lines))
" 2>/dev/null)

if [ -n "$CONTEXT" ]; then
  jq -n --arg ctx "$CONTEXT" '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: $ctx
    }
  }'
fi

exit 0
'''

PRE_TOOL_USE_HOOK = '''#!/bin/bash
# Cortex Claude — PreToolUse hook (Bash only)
# Rewrites a small set of known-verbose git/ls commands to compact,
# information-equivalent flags before execution, to reduce the tokens the
# agent has to read. This only rewrites *exact known patterns* it recognizes
# as safe (no flags that would change semantics) — anything else passes
# through unmodified. It never blocks or denies; worst case is a no-op.

INPUT=$(cat)

python3 -c "
import json, sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if data.get('tool_name') != 'Bash':
    sys.exit(0)

ti = data.get('tool_input', {}) or {}
cmd = ti.get('command', '')
if not isinstance(cmd, str):
    sys.exit(0)

stripped = cmd.strip()

# (exact command or bare prefix with no args) -> compact replacement.
# Conservative on purpose: only rewrite when we recognize the *whole*
# command, so we never clobber flags the caller already chose.
REWRITES = {
    'git status': 'git status --short --branch',
    'git log': 'git log --oneline -n 20',
    'git diff': 'git diff --stat',
    'git branch': 'git branch --list',
}

new_cmd = REWRITES.get(stripped)
if new_cmd is None or new_cmd == stripped:
    sys.exit(0)

updated_input = dict(ti)
updated_input['command'] = new_cmd

print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'allow',
        'updatedInput': updated_input,
    }
}))
" <<< "$INPUT"

exit 0
'''

POST_TOOL_USE_HOOK = '''#!/bin/bash
CORTEX_HOME="${CORTEX_HOME:-$HOME/.cortex-claude}"
SOCKET="$CORTEX_HOME/cortex.sock"

[ ! -S "$SOCKET" ] && exit 0

INPUT=$(cat)

(echo "$INPUT" | python3 -c "
import json, socket, sys, os

data = json.load(sys.stdin)
tool = data.get('tool_name', '')

if 'cortex' in tool.lower():
    sys.exit(0)

ti = data.get('tool_input', {})
tr = str(data.get('tool_response', ''))[:1000]
cwd = data.get('cwd', '.')

import re
def strip_private(t):
    t = re.sub(r'<private>.*?</private>', '', t, flags=re.DOTALL|re.IGNORECASE)
    return re.sub(r'<private\\s*/?>', '', t, flags=re.IGNORECASE).strip()

tr = strip_private(tr)
for k, v in list(ti.items()):
    if isinstance(v, str):
        ti[k] = strip_private(v)

if len(tr) < 20:
    sys.exit(0)

content = None
tags = ['auto-capture']

if tool == 'Bash':
    cmd = str(ti.get('command', ''))[:150]
    noise = ('ls', 'cd ', 'pwd', 'echo ', 'which ', 'cat ', 'head ', 'tail ', 'mkdir', 'touch ', 'chmod', 'true', 'false', 'test ')
    if any(cmd.startswith(n) for n in noise) or not cmd:
        sys.exit(0)
    content = f'Command: {cmd}' + chr(10) + f'Result: {tr[:500]}'
    tags.append('bash')
elif tool == 'Read':
    path = ti.get('file_path', '')
    content = f'Read file: {path}' + chr(10) + f'Preview: {tr[:300]}'
    tags.append('file-read')
elif tool in ('Edit', 'Write'):
    path = ti.get('file_path', '')
    old = str(ti.get('old_string', ''))[:100]
    new = str(ti.get('new_string', ''))[:100]
    if old and new:
        content = f'Edited {path}: replaced \\\"{old}\\\" with \\\"{new}\\\"'
    elif tool == 'Write':
        content = f'Created file: {path}'
    else:
        content = f'Modified file: {path}'
    tags.append('file-change')
elif tool == 'Grep':
    pattern = ti.get('pattern', '')
    path = ti.get('path', '')
    content = f'Search \\\"{pattern}\\\" in {path}' + chr(10) + f'Results: {tr[:500]}'
    tags.append('search')
elif tool == 'Glob':
    pattern = ti.get('pattern', '')
    content = f'File search: {pattern}' + chr(10) + f'Found: {tr[:500]}'
    tags.append('search')
elif tool == 'Agent':
    prompt = str(ti.get('prompt', ''))[:200]
    content = f'Agent task: {prompt}' + chr(10) + f'Result: {tr[:500]}'
    tags.append('agent')
elif tool.startswith('mcp__'):
    parts = tool.split('__')
    server = parts[1] if len(parts) > 1 else 'unknown'
    method = parts[2] if len(parts) > 2 else 'unknown'
    content = f'MCP {server}.{method}' + chr(10) + f'Input: {json.dumps(ti)[:200]}' + chr(10) + f'Result: {tr[:400]}'
    tags.append('mcp')
    tags.append(server)
elif tool in ('WebSearch', 'WebFetch'):
    query = ti.get('query', ti.get('url', ''))
    content = f'{tool}: {query}' + chr(10) + f'Result: {tr[:500]}'
    tags.append('web')
else:
    content = f'{tool}: {json.dumps(ti)[:150]}' + chr(10) + f'Result: {tr[:400]}'
    tags.append(tool.lower())

if not content:
    sys.exit(0)

sock_path = os.path.expanduser('$SOCKET')

def send(payload):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(sock_path)
        s.sendall(json.dumps(payload).encode())
        s.shutdown(socket.SHUT_WR)
        s.recv(512)
        s.close()
    except Exception:
        pass

send({'action':'save','content':content,'tags':tags,'cwd':cwd})

CODE_EXTS = ('.py','.js','.mjs','.cjs','.jsx','.ts','.tsx','.go','.java','.swift','.kt','.kts')
if tool in ('Read', 'Edit', 'Write'):
    file_path = ti.get('file_path', '')
    if file_path and file_path.lower().endswith(CODE_EXTS):
        send({'action':'index_code','path':file_path,'cwd':cwd})
") &

exit 0
'''


def _print(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  [ok] {msg}")


def _skip(msg: str) -> None:
    print(f"  [skip] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def run_setup() -> None:
    print()
    print("  Cortex Claude Setup")
    print("  ====================")
    print()

    # Tracks (step_name, ok, detail) for every step below, so the summary
    # at the end can tell the user exactly what worked and what didn't
    # instead of silently swallowing failures — this is what made it hard
    # for users to tell why an install "didn't work".
    results: list[tuple[str, bool, str]] = []

    # 1. Create data directory
    try:
        CORTEX_HOME.mkdir(parents=True, exist_ok=True)
        (CORTEX_HOME / "scopes").mkdir(exist_ok=True)
        _ok(f"Data directory: {CORTEX_HOME}")
        results.append(("Data directory", True, ""))
    except Exception as e:
        _fail(f"Data directory: {e}")
        results.append(("Data directory", False, str(e)))

    # 2. Install hooks
    try:
        HOOKS_DIR.mkdir(parents=True, exist_ok=True)

        session_start = HOOKS_DIR / "session-start.sh"
        session_start.write_text(SESSION_START_HOOK)
        session_start.chmod(session_start.stat().st_mode | stat.S_IEXEC)

        pre_tool_use = HOOKS_DIR / "pre-tool-use.sh"
        pre_tool_use.write_text(PRE_TOOL_USE_HOOK)
        pre_tool_use.chmod(pre_tool_use.stat().st_mode | stat.S_IEXEC)

        post_tool_use = HOOKS_DIR / "post-tool-use.sh"
        post_tool_use.write_text(POST_TOOL_USE_HOOK)
        post_tool_use.chmod(post_tool_use.stat().st_mode | stat.S_IEXEC)

        _ok(f"Hooks installed: {HOOKS_DIR}")
        results.append(("Hooks installed", True, ""))
    except Exception as e:
        _fail(f"Hooks installed: {e}")
        results.append(("Hooks installed", False, str(e)))
        session_start = HOOKS_DIR / "session-start.sh"
        pre_tool_use = HOOKS_DIR / "pre-tool-use.sh"
        post_tool_use = HOOKS_DIR / "post-tool-use.sh"

    # 3. Configure Claude Code MCP (global)
    try:
        mcp_config = {}
        if CLAUDE_CONFIG.exists():
            try:
                with open(CLAUDE_CONFIG) as f:
                    mcp_config = json.load(f)
            except json.JSONDecodeError:
                mcp_config = {}

        # Use the installed `cortex-claude` binary directly rather than
        # "python3 -m cortex_claude": when installed via `uv tool install`
        # (or any isolated venv), the system's bare `python3` may not have
        # cortex_claude importable at all — it lives in the tool's own
        # venv. shutil.which resolves the absolute path so Claude Code
        # doesn't depend on PATH resolution at MCP launch time.
        cortex_bin = shutil.which("cortex-claude") or "cortex-claude"
        mcp_config.setdefault("mcpServers", {})["cortex"] = {
            "type": "stdio",
            "command": cortex_bin,
            "args": [],
        }

        with open(CLAUDE_CONFIG, "w") as f:
            json.dump(mcp_config, f, indent=2)

        _ok(f"MCP server configured: {CLAUDE_CONFIG}")
        results.append(("MCP server configured", True, ""))
    except Exception as e:
        _fail(f"MCP server configured: {e}")
        results.append(("MCP server configured", False, str(e)))

    # 4. Configure hooks in Claude settings (global)
    try:
        CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)

        settings = {}
        if CLAUDE_SETTINGS.exists():
            try:
                with open(CLAUDE_SETTINGS) as f:
                    settings = json.load(f)
            except json.JSONDecodeError:
                settings = {}

        hooks = settings.setdefault("hooks", {})

        hooks["SessionStart"] = [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": str(session_start),
                        "timeout": 10,
                    }
                ],
            }
        ]

        hooks["PreToolUse"] = [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": str(pre_tool_use),
                        "timeout": 5,
                    }
                ],
            }
        ]

        hooks["PostToolUse"] = [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": str(post_tool_use),
                        "async": True,
                        "timeout": 30,
                    }
                ],
            }
        ]

        with open(CLAUDE_SETTINGS, "w") as f:
            json.dump(settings, f, indent=2)

        _ok(f"Hooks configured: {CLAUDE_SETTINGS}")
        results.append(("Hooks configured in settings.json", True, ""))
    except Exception as e:
        _fail(f"Hooks configured: {e}")
        results.append(("Hooks configured in settings.json", False, str(e)))

    # 5. Create/update CLAUDE.md
    try:
        CLAUDE_MD.parent.mkdir(parents=True, exist_ok=True)

        cortex_marker = "# Cortex Memory"
        if CLAUDE_MD.exists():
            existing = CLAUDE_MD.read_text()
            if cortex_marker in existing:
                _skip(f"CLAUDE.md already has Cortex instructions")
            else:
                with open(CLAUDE_MD, "a") as f:
                    f.write("\n\n" + CLAUDE_MD_CONTENT)
                _ok(f"Cortex instructions appended to {CLAUDE_MD}")
        else:
            CLAUDE_MD.write_text(CLAUDE_MD_CONTENT)
            _ok(f"CLAUDE.md created: {CLAUDE_MD}")
        results.append(("CLAUDE.md instructions", True, ""))
    except Exception as e:
        _fail(f"CLAUDE.md instructions: {e}")
        results.append(("CLAUDE.md instructions", False, str(e)))

    # 6. Download spaCy model
    _print("Downloading spaCy model (en_core_web_sm)...")
    try:
        import spacy
        try:
            spacy.load("en_core_web_sm")
            _skip("spaCy model already installed")
        except OSError:
            proc = subprocess.run(
                [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip()[-500:] or "spacy download failed")
            _ok("spaCy model downloaded")
        results.append(("spaCy model (en_core_web_sm)", True, ""))
    except ImportError:
        _fail("spaCy not installed — fact extraction will be degraded")
        results.append(("spaCy model (en_core_web_sm)", False, "spacy not importable"))
    except Exception as e:
        _fail(f"spaCy model download: {e}")
        results.append(("spaCy model (en_core_web_sm)", False, str(e)))

    # 7. Pre-warm embedding model
    _print("Downloading embedding model (all-MiniLM-L6-v2)...")
    try:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer("all-MiniLM-L6-v2")
        _ok("Embedding model ready")
        results.append(("Embedding model (all-MiniLM-L6-v2)", True, ""))
    except Exception as e:
        _fail(f"Embedding model download: {e}")
        results.append(("Embedding model (all-MiniLM-L6-v2)", False, str(e)))

    # 8. Start daemon
    _print("Starting Cortex daemon...")
    try:
        from cortex_claude.daemon import ensure_running, is_running
        ensure_running()
        if is_running():
            _ok("Daemon running")
            results.append(("Background daemon", True, ""))
        else:
            _print("Daemon may take a few seconds to start")
            results.append(("Background daemon", True, "starting"))
    except Exception as e:
        _fail(f"Daemon start: {e}")
        results.append(("Background daemon", False, str(e)))

    # Summary
    print()
    failed = [(name, detail) for name, ok, detail in results if not ok]
    spacy_failed = any(name.startswith("spaCy model") and not ok for name, ok, _ in results)
    embedding_failed = any(name.startswith("Embedding model") and not ok for name, ok, _ in results)
    print(f"  Setup finished: {len(results) - len(failed)}/{len(results)} steps OK")
    if failed:
        print()
        print("  Failed steps:")
        for name, detail in failed:
            print(f"    - {name}: {detail}")
        print()
        print("  cortex-claude setup is safe to re-run after fixing the issue above.")
        if spacy_failed or embedding_failed:
            print()
            print("  Model downloads most commonly fail due to network/proxy/firewall")
            print("  restrictions. You can retry just the failed step(s) manually:")
            if spacy_failed:
                print("    uv run python -m spacy download en_core_web_sm")
            if embedding_failed:
                print("    uv run python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')\"")
        print()
        return

    # Done
    print()
    print("  Setup complete!")
    print()
    print("  Cortex is now configured globally for Claude Code.")
    print("  Restart Claude Code to activate.")
    print()
    print("  Usage:")
    print("    Just talk to Claude — memories are captured automatically.")
    print("    Use 'cortex_recall', 'cortex_facts', 'cortex_traverse' to query.")
    print()
