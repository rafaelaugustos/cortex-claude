#!/bin/bash
# Cortex Claude — PostToolUse hook
# Sends tool results to daemon via Unix socket.
# Uses only stdlib Python — no cortex_claude imports, instant startup.

CORTEX_HOME="${CORTEX_HOME:-$HOME/.cortex-claude}"
SOCKET="$CORTEX_HOME/cortex.sock"

# No daemon = no save
[ ! -S "$SOCKET" ] && exit 0

# Pipe stdin to a lightweight Python script in background
python3 -c "
import json, socket, sys, os

data = json.load(sys.stdin)
tool = data.get('tool_name', '')

if tool not in ('Bash', 'Read', 'Grep', 'Edit', 'Write'):
    sys.exit(0)
if tool.startswith('mcp__cortex') or tool.startswith('cortex_'):
    sys.exit(0)

ti = data.get('tool_input', {})
tr = str(data.get('tool_response', ''))[:800]
cwd = data.get('cwd', '.')

if len(tr) < 30:
    sys.exit(0)

if tool == 'Bash':
    cmd = str(ti.get('command', ''))[:100]
    if cmd.split()[0] in ('ls','cd','pwd','echo','which','cat','head','tail') if cmd else True:
        sys.exit(0)
    content = 'Command: ' + cmd + '\nResult: ' + tr[:400]
    tags = ['auto-capture', 'bash']
elif tool == 'Read':
    content = 'Read file: ' + ti.get('file_path', '')
    tags = ['auto-capture', 'file-read']
elif tool in ('Edit', 'Write'):
    content = 'Modified file: ' + ti.get('file_path', '')
    tags = ['auto-capture', 'file-change']
elif tool == 'Grep':
    content = 'Search: ' + ti.get('pattern', '') + '\nResults: ' + tr[:400]
    tags = ['auto-capture', 'search']
else:
    sys.exit(0)

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(os.path.expanduser('$SOCKET'))
    s.sendall(json.dumps({'action':'save','content':content,'tags':tags,'cwd':cwd}).encode())
    s.shutdown(socket.SHUT_WR)
    s.recv(512)
    s.close()
except Exception:
    pass
" &

exit 0
