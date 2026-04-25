#!/bin/bash
# Cortex Claude — PostToolUse hook
# Auto-captures all tool results to Cortex memory via daemon.

CORTEX_HOME="${CORTEX_HOME:-$HOME/.cortex-claude}"
SOCKET="$CORTEX_HOME/cortex.sock"

[ ! -S "$SOCKET" ] && exit 0

# Read stdin BEFORE backgrounding
INPUT=$(cat)

# Background the processing
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
    return re.sub(r'<private\s*/?>', '', t, flags=re.IGNORECASE).strip()

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
    content = f'Command: {cmd}\nResult: {tr[:500]}'
    tags.append('bash')

elif tool == 'Read':
    path = ti.get('file_path', '')
    content = f'Read file: {path}\nPreview: {tr[:300]}'
    tags.append('file-read')

elif tool in ('Edit', 'Write'):
    path = ti.get('file_path', '')
    old = str(ti.get('old_string', ''))[:100]
    new = str(ti.get('new_string', ''))[:100]
    if old and new:
        content = f'Edited {path}: replaced \"{old}\" with \"{new}\"'
    elif tool == 'Write':
        content = f'Created file: {path}'
    else:
        content = f'Modified file: {path}'
    tags.append('file-change')

elif tool == 'Grep':
    pattern = ti.get('pattern', '')
    path = ti.get('path', '')
    content = f'Search \"{pattern}\" in {path}\nResults: {tr[:500]}'
    tags.append('search')

elif tool == 'Glob':
    pattern = ti.get('pattern', '')
    content = f'File search: {pattern}\nFound: {tr[:500]}'
    tags.append('search')

elif tool == 'Agent':
    prompt = str(ti.get('prompt', ''))[:200]
    content = f'Agent task: {prompt}\nResult: {tr[:500]}'
    tags.append('agent')

elif tool.startswith('mcp__'):
    parts = tool.split('__')
    server = parts[1] if len(parts) > 1 else 'unknown'
    method = parts[2] if len(parts) > 2 else 'unknown'
    content = f'MCP {server}.{method}\nInput: {json.dumps(ti)[:200]}\nResult: {tr[:400]}'
    tags.append('mcp')
    tags.append(server)

elif tool in ('WebSearch', 'WebFetch'):
    query = ti.get('query', ti.get('url', ''))
    content = f'{tool}: {query}\nResult: {tr[:500]}'
    tags.append('web')

else:
    content = f'{tool}: {json.dumps(ti)[:150]}\nResult: {tr[:400]}'
    tags.append(tool.lower())

if not content:
    sys.exit(0)

sock_path = os.path.expanduser('$SOCKET')
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(sock_path)
    s.sendall(json.dumps({'action':'save','content':content,'tags':tags,'cwd':cwd}).encode())
    s.shutdown(socket.SHUT_WR)
    s.recv(512)
    s.close()
except Exception:
    pass
") &

exit 0
