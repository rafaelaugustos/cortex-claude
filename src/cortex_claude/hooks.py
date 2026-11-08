"""Fast Claude hooks: no model imports, external API calls, or blocking daemon startup."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from cortex_claude.core.privacy import strip_private
from cortex_claude.learning.config import LearningConfig
from cortex_claude.learning.extraction import extract_observations
from cortex_claude.learning.store import LearningStore
from cortex_claude.learning.semantic import SemanticClient, SemanticService


def _send(home: Path, payload: dict, timeout: float = .4) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(home / "cortex.sock"))
            sock.sendall(json.dumps(payload).encode())
            sock.shutdown(socket.SHUT_WR)
            response = json.loads(sock.recv(4096))
            return isinstance(response, dict) and not response.get('error') and response.get('ok') is not False
    except (OSError, ValueError):
        return False


def _start_daemon(home: Path, cwd: str) -> None:
    # The separate process owns startup and model loading. A session hook never
    # waits for it; learning/retrieval also work when it is unavailable.
    if _send(home, {"action": "ping"}, timeout=.1):
        return
    if sys.platform == 'darwin' and (Path.home() / 'Library/LaunchAgents/com.cortexclaude.daemon.plist').exists() and home.resolve() == (Path.home() / '.cortex-claude').resolve():
        try:
            result = subprocess.run(['launchctl', 'kickstart', f'gui/{os.getuid()}/com.cortexclaude.daemon'], capture_output=True, timeout=1)
            if result.returncode == 0:
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
    home.mkdir(parents=True, exist_ok=True)
    with (home / "daemon.log").open("a") as log:
        subprocess.Popen(
            [sys.executable, "-m", "cortex_claude", "daemon"],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True,
            env={**os.environ, "CORTEX_HOME": str(home), "CORTEX_INDEX_CWD": cwd},
        )


def process_event(event: str, payload: dict, home: Path, *, retrieve: bool = True) -> dict:
    config = LearningConfig.load(home)
    cwd = payload.get("cwd") or os.getcwd()
    sid = payload.get("session_id")
    if event == "SessionStart":
        if config.enabled:
            with LearningStore(home, config) as store:
                store.session(sid, cwd, reset=retrieve and payload.get("source") == "compact")
        # No random facts or repetitive tool instructions are injected here.
        return {}
    if event == "UserPromptSubmit":
        prompt = payload.get("prompt", "")
        if not config.enabled or not isinstance(prompt, str):
            return {}
        semantic = SemanticClient(home, config)
        observations = extract_observations(prompt)
        semantic.vectors([prompt, *(o.content for o in observations)])
        with LearningStore(home, config, semantic) as store:
            observed = []
            for observation in observations:
                result = store.observe(observation, cwd, sid, source="user-prompt")
                if result.get("id") and result.get("status") != "superseded":
                    observed.append(result["id"])
            result = store.context(prompt, cwd, sid, already_known=observed) if retrieve else {"context": ""}
        if result["context"]:
            return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": result["context"]}}
        return {}
    if event in {"PostToolUse", "PostToolUseFailure"}:
        tool = payload.get("tool_name", "")
        if "cortex" in tool.lower():
            return {}
        if config.enabled and tool == "Bash":
            from cortex_claude.learning.experiences import record_verification
            with LearningStore(home, config) as store:
                store.session(sid, cwd)
                record_verification(store, payload, failed=event == "PostToolUseFailure")
        if event == "PostToolUseFailure":
            return {}
        inputs = payload.get("tool_input") or {}
        from cortex_claude.reliability.events import queue_work
        send_work = (lambda request: _send(home, request)) if retrieve else (lambda request: queue_work(home, request, payload.get('_event_id')))
        if tool in {"Read", "Edit", "Write"} and isinstance(inputs.get("file_path"), str):
            send_work({"action": "index_code", "path": inputs["file_path"], "cwd": cwd})
            if tool in {"Edit", "Write"}:
                send_work({"action": "refresh_project", "cwd": cwd})
        if tool == 'apply_patch':
            for path in payload.get('changed_files', []):
                send_work({'action': 'index_code', 'path': path, 'cwd': cwd})
            if payload.get('changed_files'):
                send_work({'action': 'refresh_project', 'cwd': cwd})
            send_work({'action': 'refresh_project', 'cwd': cwd})
        if config.capture_tools and tool not in {"Bash", "Read", "Edit", "Write", "apply_patch", "Grep", "Glob", "ToolSearch", "TaskCreate", "TaskUpdate", "TaskList", "StructuredOutput"}:
            # Redact the entire payload before *any* clipping. Otherwise a
            # truncated closing tag turns a private span into public text.
            response = payload.get("tool_response", "")
            text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
            text = strip_private(text)
            if len(text) >= 60:
                send_work({"action": "save", "content": f"{tool}: {text[:1200]}",
                           "tags": ["auto-capture", tool.lower()], "cwd": cwd})
        return {}
    if event == "Stop" and config.measure_usage and sid:
        from cortex_claude.learning.metrics import ingest_transcript
        transcript = payload.get("transcript_path")
        if isinstance(transcript, str) and payload.get('client', 'claude') == 'claude':
            with LearningStore(home, config) as store:
                ingest_transcript(store.conn, sid, Path(transcript))
        return {}
    return {}


def run_hook(event: str, client: str = 'claude') -> None:
    home = Path(os.environ.get("CORTEX_HOME", "~/.cortex-claude")).expanduser()
    try:
        payload = json.loads(sys.stdin.read(1_000_000))
        if not isinstance(payload, dict):
            return
        if 'cortex' in str(payload.get('tool_name', '')).lower():
            return
        from cortex_claude.reliability.events import normalize, apply
        from cortex_claude.reliability.queue import enqueue, drain
        from cortex_claude.reliability.checkpoints import startup_context
        data = normalize(event, payload, client)
        ident = f"{client}:{data.get('session_id')}:{event}:{data.get('turn_id')}:{data.get('tool_use_id')}" if data.get('turn_id') or data.get('tool_use_id') else None
        job_id = enqueue(home, 'hook', {'event': event, 'data': data}, ident)
        from cortex_claude.reliability.files import state
        import time
        state(home, **{f'client_{client}_received_at': time.time()})
        drain(home, lambda job: apply(home, job), limit=8, seconds=.6, kinds={'hook'})
        result: dict = {}
        config = LearningConfig.load(home)
        if config.enabled and event in {'SessionStart', 'UserPromptSubmit'}:
            with LearningStore(home, config, SemanticClient(home, config)) as store:
                sid = store.session(data.get('session_id'), data['cwd'], reset=event == 'SessionStart' and data.get('source') in {'compact', 'resume'})
                if event == 'SessionStart':
                    result = startup_context(store, data['cwd'], sid)
                else:
                    observed = [row[0] for row in store.conn.execute("SELECT e.lesson_id FROM evidence e JOIN lessons l ON l.id=e.lesson_id WHERE e.session_id=? AND e.source='user-prompt' AND l.content=?", (sid, data.get('prompt', '')))]
                    context = store.context(data.get('prompt', ''), data['cwd'], sid, already_known=observed)
                    if context['context']:
                        result = {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': context['context']}}
            if result.get('hookSpecificOutput', {}).get('additionalContext'):
                state(home, **{f'client_{client}_context_at': time.time()})
            if not (home / 'recovery' / 'receipts' / f'{job_id}.json').exists():
                result['systemMessage'] = 'Cortex: este evento está salvo em disco, mas o processamento da memória está pendente.'
        if result or (client == 'codex' and event == 'Stop'):
            print(json.dumps(result, ensure_ascii=False))
        if event == 'SessionStart':
            _start_daemon(home, data['cwd'])
    except Exception as error:
        # Hook failures must not block user prompts. Record the type and
        # message (not the user's input) for doctor/status to expose.
        try:
            home.mkdir(parents=True, exist_ok=True)
            (home / "hook-error.log").write_text(f"{event}: {type(error).__name__}\n")
        except OSError:
            pass
        message = f'Cortex: falha ao salvar/processar memória ({type(error).__name__}). Confira Saúde no dashboard; este evento pode não ter sido salvo.'
        print(message, file=sys.stderr)
        if event not in {'PreCompact', 'PostCompact', 'SessionEnd'}:
            print(json.dumps({'systemMessage': message}))


def learning_cli(args: list[str]) -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Inspect and test Cortex's shared learning memory")
    parser.add_argument("action", choices=["status", "list", "context", "forget", "read", "prepare", "record-run"])
    parser.add_argument("value", nargs="?", default="")
    parser.add_argument("--cwd", default=os.getcwd())
    options = parser.parse_args(args)
    home = Path(os.environ.get("CORTEX_HOME", "~/.cortex-claude")).expanduser()
    config = LearningConfig.load(home)
    if options.action == "prepare":
        service = SemanticService(config)
        ready = service.prepare(download=True)
        print(json.dumps({"semantic": service.status, "model": config.semantic_model}))
        if not ready:
            raise SystemExit(1)
        return
    with LearningStore(home, config, SemanticClient(home, config)) as store:
        if options.action == "status":
            result = store.stats()
            result["database"] = str(home / "learning.db")
            error_file = home / "hook-error.log"
            result["last_hook_error"] = error_file.read_text() if error_file.exists() else None
        elif options.action == "list":
            result = store.list()
        elif options.action == "context":
            result = store.context(options.value, options.cwd, delivered=False)
        elif options.action == "read":
            from cortex_claude.learning.experiences import read_details
            result = read_details(store, options.value, options.cwd, store.current_session(options.cwd))
        elif options.action == "record-run":
            from cortex_claude.learning.metrics import record_run
            result = record_run(store.conn, json.loads(Path(options.value).read_text()))
        else:
            result = {"deleted": store.forget(options.value)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
