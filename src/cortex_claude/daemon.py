from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from cortex_claude.server.config import CortexConfig

CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / ".cortex-claude")))
SOCKET_PATH = CORTEX_HOME / "cortex.sock"
PID_PATH = CORTEX_HOME / "cortex.pid"
LOG_PATH = CORTEX_HOME / "daemon.log"


class CortexDaemon:
    def __init__(self):
        from cortex_claude.core.engine import CortexEngine

        config = CortexConfig.load()
        self._engine = CortexEngine(config=config)
        self._engine.initialize()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.read(65536), timeout=30)
            if not data:
                writer.close()
                return

            request = json.loads(data.decode())
            action = request.get("action", "")
            response = await self._dispatch(action, request)

            writer.write(json.dumps(response).encode())
            await writer.drain()
        except Exception as e:
            try:
                writer.write(json.dumps({"error": str(e)}).encode())
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()
            await asyncio.sleep(0)

    async def _dispatch(self, action: str, request: dict) -> dict:
        if action == "save":
            result = await self._engine.save(
                content=request.get("content", ""),
                tags=request.get("tags"),
                scope=request.get("scope"),
                cwd=request.get("cwd", "."),
            )
            return {"ok": True, "memory_id": result.memory_id, "tokens": result.tokens_stored}

        elif action == "recall":
            result = await self._engine.recall(
                query=request.get("query", ""),
                max_tokens=request.get("max_tokens", 200),
                scope=request.get("scope"),
                depth=request.get("depth", "auto"),
                cwd=request.get("cwd", "."),
            )
            return {
                "ok": True,
                "memories": [
                    {"content": m.content[:200], "score": m.score, "scope": m.scope}
                    for m in result.memories
                ],
                "total_tokens": result.total_tokens,
            }

        elif action == "ping":
            return {"ok": True, "status": "running"}

        return {"error": f"unknown action: {action}"}

    async def start(self):
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        PID_PATH.write_text(str(os.getpid()))

        def cleanup(sig, frame):
            SOCKET_PATH.unlink(missing_ok=True)
            PID_PATH.unlink(missing_ok=True)
            sys.exit(0)

        signal.signal(signal.SIGTERM, cleanup)
        signal.signal(signal.SIGINT, cleanup)

        server = await asyncio.start_unix_server(
            self.handle_client, path=str(SOCKET_PATH)
        )

        async with server:
            await server.serve_forever()


def is_running() -> bool:
    if not PID_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text().strip())
        os.kill(pid, 0)
        return SOCKET_PATH.exists()
    except (ProcessLookupError, ValueError, OSError):
        PID_PATH.unlink(missing_ok=True)
        SOCKET_PATH.unlink(missing_ok=True)
        return False


def ensure_running() -> None:
    if is_running():
        return

    SOCKET_PATH.unlink(missing_ok=True)
    PID_PATH.unlink(missing_ok=True)

    # Find the right Python
    project_dir = Path(__file__).resolve().parent.parent.parent
    venv_python = project_dir / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    log = open(LOG_PATH, "a")
    subprocess.Popen(
        [python_cmd, "-m", "cortex_claude", "daemon"],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=str(project_dir),
        env={**os.environ, "PYTHONPATH": str(project_dir / "src")},
    )

    for _ in range(30):
        time.sleep(0.2)
        if SOCKET_PATH.exists():
            return


def send_sync(request: dict, timeout: float = 10.0) -> dict | None:
    import socket as sock

    if not SOCKET_PATH.exists():
        return None

    try:
        s = sock.socket(sock.AF_UNIX, sock.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(str(SOCKET_PATH))
        s.sendall(json.dumps(request).encode())
        s.shutdown(sock.SHUT_WR)

        chunks = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        s.close()

        if chunks:
            return json.loads(b"".join(chunks).decode())
    except Exception:
        return None
    return None
