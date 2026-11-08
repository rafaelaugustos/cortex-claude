"""Exercise the real resident model, Unix socket and prompt subprocesses offline."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from cortex_claude.learning.store import LearningStore


def evaluate(home: Path) -> dict:
    env = {**os.environ, "CORTEX_HOME": str(home)}
    with (home / "daemon-test.log").open("w") as log:
        daemon = subprocess.Popen([sys.executable, "-m", "cortex_claude", "daemon"], env=env, stdout=log, stderr=log)
        try:
            ready = False
            for _ in range(240):
                if daemon.poll() is not None:
                    raise RuntimeError((home / "daemon-test.log").read_text()[-2000:])
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                        sock.settimeout(.5)
                        sock.connect(str(home / "cortex.sock"))
                        sock.sendall(b'{"action":"ping"}')
                        sock.shutdown(socket.SHUT_WR)
                        ready = json.loads(sock.recv(4096)).get("semantic") == "ready"
                except (OSError, ValueError):
                    pass
                if ready:
                    break
                time.sleep(.25)
            assert ready, "Resident semantic model did not become ready; run learning prepare"
            elapsed = []
            def prompt(text, sid, cwd="/synthetic/previous"):
                started = time.monotonic()
                result = subprocess.run([sys.executable, "-m", "cortex_claude", "hook", "UserPromptSubmit"],
                    input=json.dumps({"session_id": sid, "cwd": cwd, "prompt": text}), env=env,
                    capture_output=True, text=True, timeout=5)
                elapsed.append(round((time.monotonic() - started) * 1000, 2))
                assert result.returncode == 0, result.stderr
                assert not (home / "hook-error.log").exists(), (home / "hook-error.log").read_text() if (home / "hook-error.log").exists() else ""
                return json.loads(result.stdout) if result.stdout.strip() else {}
            for i, text in enumerate(["I prefer explanations that get straight to the point", "Eu prefiro explicacoes diretas ao ponto", "I prefer explanations that get straight to the point"]):
                assert prompt(text, f"evidence-{i}") == {}
            with LearningStore(home) as store:
                lessons = store.list()
                assert len(lessons) == 1, lessons
                assert lessons[0]["confirmations"] == 3 and lessons[0]["state"] == "active"
            first = prompt("Explain this architecture", "new", "/synthetic/new")
            assert "straight to the point" in first["hookSpecificOutput"]["additionalContext"]
            assert prompt("Explain this architecture", "new", "/synthetic/new") == {}
            assert prompt("Plan a beach vacation", "vacation", "/synthetic/new") == {}
            with LearningStore(home) as store:
                stats = store.stats()
            return {"checks": {"real_multilingual_paraphrases_merged": True, "three_independent_sessions": True,
                "cross_project_hook_injected": True, "second_hook_empty": True, "irrelevant_hook_empty": True},
                "subprocess_hook_ms": elapsed, "stats": stats,
                "limits": "Small offline behavioral check using the real local model and daemon; timings include hook process startup, not daemon/model startup."}
        finally:
            daemon.terminate()
            try:
                daemon.wait(timeout=10)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cx-sem-", dir="/tmp") as directory:
        result = evaluate(Path(directory))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
