from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from cortex_claude.capture import (
    CaptureContext,
    CaptureDecision,
    CaptureFilter,
    CaptureFilterConfig,
)
from cortex_claude.clustering import ClusteringConfig, ClusteringEngine
from cortex_claude.code import extract_symbols, is_supported_path
from cortex_claude.code.facts import (
    known_symbol_names,
    mention_facts,
    symbols_to_facts,
)
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
        self._capture_filter = CaptureFilter(CaptureFilterConfig.from_dict(config.capture))
        self._cluster_config = ClusteringConfig.from_dict(config.clustering)
        self._cluster_engine = ClusteringEngine(self._cluster_config)
        self._saves_since_cluster: dict[str, int] = {}
        self._last_cluster_at: dict[str, float] = {}
        self._cluster_in_flight: set[str] = set()
        self._known_symbols_cache: dict[str, set[str]] = {}

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
            content = request.get("content", "")
            tags = request.get("tags") or []

            decision, reason = self._capture_filter.decide(
                CaptureContext(content=content, tags=list(tags))
            )
            if decision == CaptureDecision.DROP:
                return {"ok": True, "dropped": True, "reason": reason}

            result = await self._engine.save(
                content=content,
                tags=tags,
                scope=request.get("scope"),
                cwd=request.get("cwd", "."),
            )

            await asyncio.to_thread(
                self._link_memory_mentions, result.memory_id, content, result.scope
            )

            self._maybe_schedule_clustering(result.scope)

            return {
                "ok": True,
                "memory_id": result.memory_id,
                "tokens": result.tokens_stored,
                "filter": reason,
            }

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

        elif action == "cluster":
            scope = request.get("scope")
            if not scope:
                return {"error": "scope required"}
            stats = await self._run_clustering(scope)
            return {
                "ok": True,
                "scope": scope,
                "assigned": stats.assigned,
                "new_clusters": stats.new_clusters,
                "relabeled": stats.relabeled,
            }

        elif action == "cluster_backfill":
            scope = request.get("scope")
            if not scope:
                return {"error": "scope required"}
            await asyncio.to_thread(self._engine.reset_clusters, scope)
            stats = await self._run_clustering(scope)
            return {
                "ok": True,
                "scope": scope,
                "backfill": True,
                "assigned": stats.assigned,
                "new_clusters": stats.new_clusters,
                "relabeled": stats.relabeled,
            }

        elif action == "index_code":
            path = request.get("path", "")
            scope = request.get("scope")
            cwd = request.get("cwd", ".")
            if not path or not is_supported_path(path):
                return {"ok": True, "skipped": True, "reason": "unsupported-path"}
            result = await asyncio.to_thread(
                self._index_code_file, path, scope, cwd
            )
            return result

        return {"error": f"unknown action: {action}"}

    def _index_code_file(self, path: str, scope: str | None, cwd: str) -> dict:
        from pathlib import Path

        p = Path(path)
        if not p.is_file():
            return {"ok": True, "skipped": True, "reason": "not-a-file"}

        try:
            size = p.stat().st_size
        except OSError:
            return {"ok": True, "skipped": True, "reason": "stat-failed"}

        if size > 1_000_000:
            return {"ok": True, "skipped": True, "reason": "too-large"}

        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {"ok": True, "skipped": True, "reason": "read-failed"}

        symbols = extract_symbols(path, content)
        if not symbols:
            return {"ok": True, "indexed": 0, "facts": 0}

        facts = symbols_to_facts(symbols)
        if not facts:
            return {"ok": True, "indexed": len(symbols), "facts": 0}

        write_scope = scope or self._engine._scope_manager.get_write_scope(cwd)
        conn = self._engine.get_scope_connection(write_scope)

        for fact in facts:
            fact.scope = write_scope

        from cortex_claude.storage import FactRepository
        FactRepository().save_batch(conn, facts)

        self._known_symbols_cache.pop(write_scope, None)

        return {
            "ok": True,
            "indexed": len(symbols),
            "facts": len(facts),
            "scope": write_scope,
        }

    def _link_memory_mentions(self, memory_id: str, content: str, scope: str) -> None:
        if not memory_id or not scope:
            return
        try:
            conn = self._engine.get_scope_connection(scope)
        except Exception:
            return

        known = self._known_symbols_cache.get(scope)
        if known is None:
            known = known_symbol_names(conn, scope)
            self._known_symbols_cache[scope] = known

        if not known:
            return

        facts = mention_facts(memory_id, content, known, scope)
        if not facts:
            return

        from cortex_claude.storage import FactRepository
        FactRepository().save_batch(conn, facts)

    def _maybe_schedule_clustering(self, scope: str | None) -> None:
        if not self._cluster_config.enabled or not scope:
            return
        if scope in self._cluster_in_flight:
            return

        self._saves_since_cluster[scope] = self._saves_since_cluster.get(scope, 0) + 1
        if self._saves_since_cluster[scope] < self._cluster_config.saves_between_runs:
            return

        last = self._last_cluster_at.get(scope, 0.0)
        if (time.time() - last) < self._cluster_config.cooldown_seconds:
            return

        self._saves_since_cluster[scope] = 0
        self._cluster_in_flight.add(scope)
        asyncio.create_task(self._run_clustering(scope))

    async def _run_clustering(self, scope: str):
        try:
            conn = self._engine.get_scope_connection(scope)
            stats = await asyncio.to_thread(self._cluster_engine.cluster_scope, conn, scope)
            self._last_cluster_at[scope] = time.time()
            return stats
        finally:
            self._cluster_in_flight.discard(scope)

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

        self._schedule_auto_backfill()

        server = await asyncio.start_unix_server(
            self.handle_client, path=str(SOCKET_PATH)
        )

        async with server:
            await server.serve_forever()

    def _schedule_auto_backfill(self) -> None:
        """On first startup after the v6 migration, seed clusters for any scope
        that has memories but no clusters yet. Runs in background so it doesn't
        block daemon startup."""
        if not self._cluster_config.enabled:
            return

        try:
            scopes = self._engine._storage.list_scopes()
        except Exception:
            return

        for scope in scopes:
            try:
                conn = self._engine.get_scope_connection(scope)
                mem_count = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE cluster_id IS NULL"
                ).fetchone()[0]
                cluster_count = conn.execute(
                    "SELECT COUNT(*) FROM clusters WHERE scope = ?",
                    (scope,),
                ).fetchone()[0]
            except Exception:
                continue

            if mem_count > 0 and cluster_count == 0:
                print(
                    f"[cortex] auto-backfill: clustering {mem_count} memories in scope '{scope}'",
                    file=sys.stderr,
                    flush=True,
                )
                self._cluster_in_flight.add(scope)
                asyncio.create_task(self._run_clustering(scope))


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
