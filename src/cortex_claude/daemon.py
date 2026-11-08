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

CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / ".cortex-claude"))).expanduser()
SOCKET_PATH = CORTEX_HOME / "cortex.sock"
PID_PATH = CORTEX_HOME / "cortex.pid"
LOG_PATH = CORTEX_HOME / "daemon.log"


class CortexDaemon:
    def __init__(self):
        from cortex_claude.core.engine import CortexEngine

        config = CortexConfig.load(CORTEX_HOME.expanduser())
        self._engine = CortexEngine(config=config)
        self._engine.initialize()
        self._capture_filter = CaptureFilter(CaptureFilterConfig.from_dict(config.capture))
        self._cluster_config = ClusteringConfig.from_dict(config.clustering)
        self._cluster_engine = ClusteringEngine(self._cluster_config)
        self._saves_since_cluster: dict[str, int] = {}
        self._last_cluster_at: dict[str, float] = {}
        self._cluster_in_flight: set[str] = set()
        self._cluster_runs_since_reassign: dict[str, int] = {}
        self._known_symbols_cache: dict[str, set[str]] = {}
        self._project_scan_in_flight: set[str] = set()
        self._project_scan_tasks: dict[str, asyncio.Task] = {}
        self._background: set[asyncio.Task] = set()
        self._clients: set[asyncio.Task] = set()
        self._stopping = asyncio.Event()
        from cortex_claude.learning.config import LearningConfig
        from cortex_claude.learning.semantic import SemanticService
        self._semantic = SemanticService(LearningConfig.load(CORTEX_HOME))

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        task = asyncio.current_task()
        clients = getattr(self, '_clients', None)
        if clients is not None and task:
            clients.add(task)
        try:
            async def read_request():
                chunks, size = [], 0
                while chunk := await reader.read(65536):
                    size += len(chunk)
                    if size > 1_000_000:
                        raise ValueError("Request too large")
                    chunks.append(chunk)
                return b"".join(chunks)
            data = await asyncio.wait_for(read_request(), timeout=5)
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
            if clients is not None and task:
                clients.discard(task)
            await asyncio.sleep(0)

    async def _dispatch(self, action: str, request: dict) -> dict:
        if action in {'ping', 'learning_vectors', 'index_project', 'refresh_project', 'cluster', 'cluster_backfill'}:
            return await self._dispatch_unlocked(action, request)
        async with self._database_lock():
            return await self._dispatch_unlocked(action, request)

    def _database_lock(self) -> asyncio.Lock:
        if not hasattr(self, '_engine_lock'):
            self._engine_lock = asyncio.Lock()
        return self._engine_lock

    def _spawn(self, coroutine) -> asyncio.Task:
        if not hasattr(self, '_background'):
            self._background = set()
        task = asyncio.create_task(coroutine)
        self._background.add(task)
        def finished(value):
            self._background.discard(value)
            if not value.cancelled():
                value.exception()  # Errors are logged by workers; consume fire-and-forget exceptions.
        task.add_done_callback(finished)
        return task

    async def _dispatch_unlocked(self, action: str, request: dict) -> dict:
        if action == "learning_vectors":
            service = self._semantic
            if request.get("model") != service.config.semantic_model or service.status != "ready":
                return {"status": service.status}
            vectors = await asyncio.to_thread(service.encode, request.get("texts", []))
            return {"model": service.config.semantic_model, "vectors": vectors}

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

            from cortex_claude.core.privacy import strip_private
            await asyncio.to_thread(
                self._link_memory_mentions, result.memory_id, strip_private(content), result.scope
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
            return {"ok": True, "status": "running", "semantic": self._semantic.status}

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
            async with self._database_lock():
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

        elif action == "index_project":
            cwd = request.get("cwd", ".")
            stats = self._maybe_index_project(cwd)
            return {"ok": True, **stats}

        elif action == "refresh_project":
            self._schedule_project_profile(request.get("cwd", "."))
            return {"ok": True, "scheduled": True}

        return {"error": f"unknown action: {action}"}

    def _maybe_index_project(self, cwd: str) -> dict:
        """Fire-and-forget whole-project code scan, triggered from
        SessionStart. Only runs once per scope: if the scope already has
        code-graph facts (relation='defined_in'), this is a no-op — the
        existing incremental Read/Edit indexing keeps it fresh from there.
        """
        self._schedule_project_profile(cwd)
        scope = self._engine._scope_manager.auto_project_scope(cwd)

        if scope in self._project_scan_in_flight:
            return {"skipped": "already-in-flight", "scope": scope}

        conn = self._engine.get_scope_connection(scope)
        already_indexed = conn.execute(
            "SELECT 1 FROM facts WHERE scope = ? AND relation = 'defined_in' LIMIT 1",
            (scope,),
        ).fetchone()
        if already_indexed:
            return {"skipped": "already-indexed", "scope": scope}

        self._project_scan_in_flight.add(scope)
        task = self._spawn(self._run_project_scan(cwd, scope))
        self._project_scan_tasks[scope] = task
        return {"started": True, "scope": scope}

    def _schedule_project_profile(self, cwd: str) -> None:
        from cortex_claude.learning.store import context_origin
        root = Path(context_origin(cwd))
        if not ((root / '.git').exists() or any((root / name).is_file() for name in ('package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod'))):
            return
        tasks = getattr(self, '_profile_tasks', None)
        if tasks is None:
            tasks = self._profile_tasks = {}
        if str(root) in tasks and not tasks[str(root)].done():
            return
        def scan():
            from cortex_claude.learning.projects import refresh_project
            from cortex_claude.learning.store import LearningStore
            with LearningStore(self._engine._base_path) as store:
                refresh_project(store, str(root))
        async def run():
            try:
                await asyncio.to_thread(scan)
            except (OSError, ValueError) as error:
                print(f'[cortex] project memory: {type(error).__name__}', file=sys.stderr)
                raise
            finally:
                tasks.pop(str(root), None)
        tasks[str(root)] = self._spawn(run())

    async def _run_project_scan(self, cwd: str, scope: str) -> None:
        from cortex_claude.server.tools.code import handle_index_code

        try:
            print(
                f"[cortex] project scan: indexing '{cwd}' into scope '{scope}'",
                file=sys.stderr,
                flush=True,
            )
            async with self._database_lock():
                result = await handle_index_code(
                    self._engine, cwd=cwd, path=cwd, scope=scope, max_files=2000,
                )
            print(f"[cortex] project scan done: {result}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[cortex] project scan failed: {e}", file=sys.stderr, flush=True)
            raise
        finally:
            self._project_scan_in_flight.discard(scope)

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

        write_scope = scope or self._engine._scope_manager.auto_project_scope(cwd)
        conn = self._engine.get_scope_connection(write_scope)

        for fact in facts:
            fact.scope = write_scope

        from cortex_claude.storage import FactRepository
        repo = FactRepository()
        # Prevent stale facts from accumulating across repeated auto-index
        # runs (this path fires on every Read/Edit of a code file).
        repo.delete_by_source_file(conn, write_scope, str(path))
        repo.save_batch(conn, facts)

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
        self._spawn(self._run_clustering(scope))

    async def _run_clustering(self, scope: str):
        try:
            async with self._database_lock():
                conn = self._engine.get_scope_connection(scope)
                stats = await asyncio.to_thread(self._cluster_engine.cluster_scope, conn, scope)
                self._last_cluster_at[scope] = time.time()
                self._maybe_reassign_stale(conn, scope)
            return stats
        finally:
            self._cluster_in_flight.discard(scope)

    def _maybe_reassign_stale(self, conn, scope: str) -> None:
        reassign_after = self._cluster_config.reassign_after_runs
        if reassign_after <= 0:
            return

        self._cluster_runs_since_reassign[scope] = (
            self._cluster_runs_since_reassign.get(scope, 0) + 1
        )
        if self._cluster_runs_since_reassign[scope] < reassign_after:
            return

        self._cluster_runs_since_reassign[scope] = 0
        self._cluster_engine.reassign_stale(conn, scope)

    async def start(self, process_lock=None):
        import fcntl
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = process_lock or (SOCKET_PATH.parent / "daemon.lock").open("a")
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock_file.close()
            self._engine.close()
            return
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        PID_PATH.write_text(str(os.getpid()))

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._stopping.set)

        self._schedule_auto_backfill()
        self._semantic_task = asyncio.create_task(self._maintain_semantics())
        self._recovery_task = asyncio.create_task(self._maintain_recovery())

        server = await asyncio.start_unix_server(
            self.handle_client, path=str(SOCKET_PATH)
        )
        SOCKET_PATH.chmod(0o600)
        if cwd := os.environ.get("CORTEX_INDEX_CWD"):
            self._maybe_index_project(cwd)

        try:
            async with server:
                await self._stopping.wait()
        finally:
            server.close()
            await server.wait_closed()
            self._semantic_task.cancel()
            tasks = [self._semantic_task, self._recovery_task, *self._background, *self._clients]
            if tasks:
                done, unfinished = await asyncio.wait(tasks, timeout=15)
                for task in unfinished:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            self._engine.close()
            SOCKET_PATH.unlink(missing_ok=True)
            if PID_PATH.exists() and PID_PATH.read_text().strip() == str(os.getpid()):
                PID_PATH.unlink()
            self._lock_file.close()

    async def _durable_work(self, request: dict) -> None:
        from cortex_claude.learning.store import context_origin
        action = request.get('action', '')
        if action in {'index_project', 'refresh_project'}:
            cwd = request.get('cwd', '.')
            if not Path(cwd).is_dir():
                return
            result = await self._dispatch(action, request)
            tasks = []
            profile = getattr(self, '_profile_tasks', {}).get(context_origin(cwd))
            if profile:
                tasks.append(profile)
            code = self._project_scan_tasks.get(result.get('scope', '')) if action == 'index_project' else None
            if code:
                tasks.append(code)
            if tasks:
                await asyncio.gather(*tasks)
        else:
            result = await self._dispatch(action, request)
        if result.get('error') or result.get('ok') is False:
            raise RuntimeError('Deferred operation failed')

    async def _maintain_recovery(self) -> None:
        from cortex_claude.learning.store import LearningStore
        from cortex_claude.reliability.events import apply
        from cortex_claude.reliability.queue import drain, prune_receipts
        from cortex_claude.reliability.files import read_json, state
        from cortex_claude.reliability.backups import create, due, test_restore
        loop = asyncio.get_running_loop()
        def handler(job):
            if job['kind'] == 'hook':
                apply(CORTEX_HOME, job)
            elif job['kind'] == 'daemon':
                future = asyncio.run_coroutine_threadsafe(self._durable_work(job['payload']), loop)
                try:
                    future.result(timeout=120)
                except Exception:
                    future.cancel()
                    raise
            else:
                raise ValueError('Unknown pending operation')
        last_cleanup = 0
        last_diagnostic = 0
        while not self._stopping.is_set():
            try:
                with LearningStore(CORTEX_HOME):
                    pass
                await asyncio.to_thread(drain, CORTEX_HOME, handler, seconds=2)
                await asyncio.to_thread(state, CORTEX_HOME, heartbeat_at=time.time())
                current = read_json(CORTEX_HOME / 'recovery' / 'state.json')
                if due(CORTEX_HOME) and time.time() - current.get('last_backup_attempt', 0) > 300:
                    await asyncio.to_thread(state, CORTEX_HOME, last_backup_attempt=time.time())
                    result = await asyncio.to_thread(create, CORTEX_HOME, reason='scheduled')
                    await asyncio.to_thread(test_restore, CORTEX_HOME, result['id'])
                if time.time() - last_cleanup > 3600:
                    await asyncio.to_thread(prune_receipts, CORTEX_HOME)
                    last_cleanup = time.time()
                await asyncio.to_thread(state, CORTEX_HOME, service_error=None, heartbeat_at=time.time())
                if time.time() - last_diagnostic > 60:
                    from cortex_claude.reliability.diagnostics import sample
                    await asyncio.to_thread(sample, CORTEX_HOME)
                    last_diagnostic = time.time()
            except Exception as error:
                try:
                    await asyncio.to_thread(state, CORTEX_HOME, service_error={'type': type(error).__name__, 'at': time.time()})
                except OSError:
                    pass
                print(f'[cortex] recovery: {type(error).__name__}', file=sys.stderr)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    async def _maintain_semantics(self) -> None:
        from cortex_claude.learning.config import LearningConfig
        from cortex_claude.learning.semantic import SemanticService
        while True:
            try:
                config = LearningConfig.load(CORTEX_HOME)
                if (config.semantic_model, config.semantic_enabled) != (self._semantic.config.semantic_model, self._semantic.config.semantic_enabled):
                    self._semantic = SemanticService(config)
                if self._semantic.status != "ready":
                    await asyncio.to_thread(self._semantic.prepare)
                if self._semantic.status == "ready":
                    await asyncio.to_thread(self._semantic.backfill, CORTEX_HOME)
                status = CORTEX_HOME / "semantic-status.tmp"
                status.write_text(json.dumps({"state": self._semantic.status, "model": self._semantic.config.semantic_model, "updated_at": time.time()}))
                status.replace(CORTEX_HOME / "semantic-status.json")
            except Exception as error:
                print(f"[cortex] semantic maintenance: {type(error).__name__}", file=sys.stderr)
            await asyncio.sleep(30)

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
                self._spawn(self._run_clustering(scope))


def is_running() -> bool:
    response = send_sync({'action': 'ping'}, timeout=.3)
    return bool(response and response.get('status') == 'running')


def ensure_running() -> None:
    if is_running():
        return

    CORTEX_HOME.mkdir(parents=True, exist_ok=True)

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
        if is_running():
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
