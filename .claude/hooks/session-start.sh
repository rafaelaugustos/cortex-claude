#!/bin/bash
# Cortex Claude — SessionStart hook
# 1. Injects memory context (instant, direct SQLite)
# 2. Starts the daemon in background (pre-warms the model for PostToolUse)

INPUT=$(cat)
CWD=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd','.'))" <<< "$INPUT" 2>/dev/null)

CORTEX_HOME="${CORTEX_HOME:-$HOME/.cortex-claude}"
GLOBAL_DB="$CORTEX_HOME/global.db"

# Start daemon in background (pre-warm model for fast PostToolUse)
SOCKET="$CORTEX_HOME/cortex.sock"
if [ ! -S "$SOCKET" ]; then
  VENV_PYTHON="$CWD/.venv/bin/python"
  if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
  fi
  PYTHONPATH="$CWD/src" "$VENV_PYTHON" -c "from cortex_claude.daemon import ensure_running; ensure_running()" 2>/dev/null &
fi

# Inject context (direct SQLite, no model needed)
if [ ! -f "$GLOBAL_DB" ]; then
  exit 0
fi

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
