from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import sqlite_vec

CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / ".cortex-claude")))
STATIC_DIR = (Path(__file__).parent / "static").resolve()

# Nothing the browser renders benefits from more than this, and every element
# past it costs layout time quadratically.
MAX_GRAPH_NODES = 220
MAX_GRAPH_EDGES = 400
MAX_PAGE_SIZE = 200


# ─────────────────────────────────────────────────────────────
# Connections — one per (thread, database). ThreadingHTTPServer
# hands each request its own thread and sqlite connections are
# not safe to share across them.
# ─────────────────────────────────────────────────────────────

_local = threading.local()


def _scope_databases() -> list[tuple[str, Path]]:
    dbs: list[tuple[str, Path]] = []
    global_db = CORTEX_HOME / "global.db"
    if global_db.exists():
        dbs.append(("global", global_db))
    scopes_dir = CORTEX_HOME / "scopes"
    if scopes_dir.is_dir():
        for f in sorted(scopes_dir.glob("*.db")):
            dbs.append((f.stem.replace("__", ":"), f))
    return dbs


def _connect(db_path: Path) -> sqlite3.Connection:
    cache: dict[str, sqlite3.Connection] = getattr(_local, "conns", None) or {}
    _local.conns = cache
    key = str(db_path)
    conn = cache.get(key)
    if conn is None:
        conn = sqlite3.connect(key, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        # memory_vectors is a vec0 virtual table: without the extension the
        # table is unreadable and deletes against it fail, orphaning vectors.
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
        cache[key] = conn
    return conn


def _targets(scope: str | None) -> list[tuple[str, Path]]:
    dbs = _scope_databases()
    if scope and scope != "all":
        return [(n, p) for n, p in dbs if n == scope]
    return dbs


def _query(scope: str | None, sql: str, params: tuple = ()) -> list[dict]:
    rows: list[dict] = []
    for name, path in _targets(scope):
        try:
            for row in _connect(path).execute(sql, params):
                d = dict(row)
                d["_scope"] = name
                rows.append(d)
        except sqlite3.Error:
            continue
    return rows


# ─────────────────────────────────────────────────────────────
# Filters — one WHERE builder shared by list, count and cleanup
# so a preview can never disagree with what gets deleted.
# ─────────────────────────────────────────────────────────────

SORTS = {
    "recent": "created_at DESC",
    "oldest": "created_at ASC",
    "relevance": "decay_score DESC",
    "accessed": "accessed_at DESC",
    "largest": "LENGTH(content) DESC",
}


def _memory_where(
    tag: str | None = None,
    cluster: int | None = None,
    query: str | None = None,
    pattern: str | None = None,
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []

    if tag:
        clauses.append("tags LIKE ?")
        params.append(f'%"{tag}"%')
    if cluster is not None:
        clauses.append("cluster_id = ?")
        params.append(cluster)
    if query:
        clauses.append("(LOWER(content) LIKE ? OR LOWER(tags) LIKE ?)")
        like = f"%{query.lower()}%"
        params.extend([like, like])
    if pattern:
        clauses.append("content REGEXP ?")
        params.append(pattern)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _register_regexp(conn: sqlite3.Connection) -> None:
    def _re(pattern: str, value: str) -> bool:
        if value is None:
            return False
        try:
            return re.search(pattern, value, re.IGNORECASE) is not None
        except re.error:
            return False

    conn.create_function("REGEXP", 2, _re)


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

MEMORY_COLS = (
    "id, content, summary, tags, scope, cluster_id, LENGTH(content) AS size, "
    "created_at, accessed_at, access_count, decay_score"
)


def api_overview() -> dict:
    scopes = []
    total_mem = total_facts = total_size = 0

    for name, path in _scope_databases():
        try:
            conn = _connect(path)
            mem = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            facts = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            clusters = conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]
        except sqlite3.Error:
            continue
        size = path.stat().st_size if path.exists() else 0
        scopes.append(
            {
                "name": name,
                "memories": mem,
                "facts": facts,
                "clusters": clusters,
                "size": size,
            }
        )
        total_mem += mem
        total_facts += facts
        total_size += size

    tag_counts: dict[str, int] = {}
    for row in _query(None, "SELECT tags, COUNT(*) c FROM memories GROUP BY tags"):
        try:
            tags = json.loads(row["tags"] or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + row["c"]

    day_ms = 86_400_000
    cutoff = int(time.time() * 1000) - 30 * day_ms
    buckets: dict[int, int] = {}
    for row in _query(
        None,
        "SELECT created_at / ? AS day, COUNT(*) c FROM memories "
        "WHERE created_at >= ? GROUP BY day",
        (day_ms, cutoff),
    ):
        buckets[row["day"]] = buckets.get(row["day"], 0) + row["c"]

    today = int(time.time() * 1000) // day_ms
    growth = [
        {"day": int((today - i) * day_ms), "count": buckets.get(today - i, 0)}
        for i in range(29, -1, -1)
    ]

    return {
        "totals": {
            "memories": total_mem,
            "facts": total_facts,
            "clusters": sum(s["clusters"] for s in scopes),
            "size": total_size,
        },
        "scopes": sorted(scopes, key=lambda s: -int(s["memories"])),
        "tags": [
            {"name": name, "count": count}
            for name, count in sorted(tag_counts.items(), key=lambda kv: -kv[1])[:24]
        ],
        "growth": growth,
    }


def api_clusters(
    scope: str | None, query: str | None, limit: int, offset: int, sort: str
) -> dict:
    order = "member_count DESC" if sort != "recent" else "updated_at DESC"
    where = ""
    params: list = []
    if query:
        where = " WHERE LOWER(label) LIKE ?"
        params.append(f"%{query.lower()}%")

    rows = _query(
        scope,
        f"SELECT id, scope, label, member_count, updated_at FROM clusters{where} "
        f"ORDER BY {order}",
        tuple(params),
    )
    total = len(rows)
    key = (lambda c: -c["member_count"]) if sort != "recent" else (lambda c: -c["updated_at"])
    rows.sort(key=key)

    return {"items": rows[offset : offset + limit], "total": total}


def _is_internal(entity: str) -> bool:
    """`memory:<uuid> -> mentions -> symbol` back-references are plumbing, not
    knowledge. They are a third of the fact table and would drown any graph
    they appear in; the memory list already says which memories mention what."""
    return not entity or entity.startswith("memory:")


def _build_graph(facts: list[dict], max_nodes: int = MAX_GRAPH_NODES) -> dict:
    """Fold triplets into a node/edge set small enough to lay out.

    Nodes are ranked by degree and cut to `max_nodes`; edges that lose an
    endpoint to the cut are dropped so the client never sees a dangling edge.
    """
    facts = [
        f
        for f in facts
        if not _is_internal(f["subject"]) and not _is_internal(f["object"])
    ]

    degree: dict[str, int] = {}
    for f in facts:
        for k in (f["subject"], f["object"]):
            if k:
                degree[k] = degree.get(k, 0) + 1

    keep = {n for n, _ in sorted(degree.items(), key=lambda kv: -kv[1])[:max_nodes]}

    edges = []
    for f in facts:
        if f["subject"] in keep and f["object"] in keep:
            edges.append(
                {
                    "source": f["subject"],
                    "target": f["object"],
                    "label": f["relation"],
                    "confidence": f["confidence"],
                }
            )
        if len(edges) >= MAX_GRAPH_EDGES:
            break

    used = {e["source"] for e in edges} | {e["target"] for e in edges}
    nodes = [
        {"id": n, "label": n, "weight": degree[n]} for n in keep if n in used
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "truncated": len(degree) > len(nodes) or len(facts) > len(edges),
        "total_nodes": len(degree),
        "total_edges": len(facts),
    }


def api_cluster_detail(cluster_id: int, scope: str | None) -> dict:
    for name, path in _targets(scope):
        try:
            conn = _connect(path)
            cluster = conn.execute(
                "SELECT id, scope, label, member_count, updated_at FROM clusters WHERE id = ?",
                (cluster_id,),
            ).fetchone()
        except sqlite3.Error:
            continue
        if cluster is None:
            continue

        facts = [
            dict(r)
            for r in conn.execute(
                "SELECT f.subject, f.relation, f.object, f.confidence "
                "FROM facts f JOIN memories m ON m.id = f.source_memory_id "
                "WHERE m.cluster_id = ? ORDER BY f.confidence DESC LIMIT 4000",
                (cluster_id,),
            )
        ]
        memories = [
            dict(r)
            for r in conn.execute(
                f"SELECT {MEMORY_COLS} FROM memories WHERE cluster_id = ? "
                "ORDER BY decay_score DESC LIMIT 50",
                (cluster_id,),
            )
        ]
        for m in memories:
            m["_scope"] = name

        return {
            "cluster": dict(cluster),
            "scope": name,
            "graph": _build_graph(facts),
            "memories": memories,
        }

    return {"error": "cluster not found"}


def api_memories(
    scope: str | None,
    tag: str | None,
    cluster: int | None,
    query: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> dict:
    where, params = _memory_where(tag=tag, cluster=cluster, query=query)
    order = SORTS.get(sort, SORTS["recent"])

    items: list[dict] = []
    total = 0
    for name, path in _targets(scope):
        try:
            conn = _connect(path)
            total += conn.execute(
                f"SELECT COUNT(*) FROM memories{where}", tuple(params)
            ).fetchone()[0]
            for row in conn.execute(
                f"SELECT {MEMORY_COLS} FROM memories{where} ORDER BY {order} "
                "LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ):
                d = dict(row)
                d["_scope"] = name
                items.append(d)
        except sqlite3.Error:
            continue

    return {"items": items[:limit], "total": total}


def api_entity(name: str) -> dict:
    like = f"%{name.lower()}%"
    facts = _query(
        None,
        "SELECT subject, relation, object, confidence, scope FROM facts "
        "WHERE (LOWER(subject) LIKE ? OR LOWER(object) LIKE ?) "
        "AND subject NOT LIKE 'memory:%' "
        "ORDER BY confidence DESC LIMIT 600",
        (like, like),
    )
    memories = _query(
        None,
        f"SELECT {MEMORY_COLS} FROM memories WHERE LOWER(content) LIKE ? "
        "ORDER BY decay_score DESC LIMIT 20",
        (like,),
    )
    return {
        "facts": facts[:120],
        "memories": memories,
        "graph": _build_graph(facts, max_nodes=70),
    }


def api_memory(memory_id: str) -> dict:
    for name, path in _scope_databases():
        try:
            conn = _connect(path)
            row = conn.execute(
                f"SELECT {MEMORY_COLS} FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        except sqlite3.Error:
            continue
        if row is None:
            continue
        facts = [
            dict(r)
            for r in conn.execute(
                "SELECT subject, relation, object, confidence FROM facts "
                "WHERE source_memory_id = ? ORDER BY confidence DESC LIMIT 100",
                (memory_id,),
            )
        ]
        memory = dict(row)
        memory["_scope"] = name
        return {"memory": memory, "facts": facts}
    return {"error": "memory not found"}


def _delete_ids(conn: sqlite3.Connection, ids: list[str]) -> int:
    """Delete memories and everything hanging off them.

    facts cascade via the foreign key and the FTS index is maintained by
    triggers, but memory_vectors is a vec0 virtual table with neither, so it
    has to be cleared explicitly.
    """
    deleted = 0
    for i in range(0, len(ids), 500):
        batch = ids[i : i + 500]
        marks = ",".join("?" for _ in batch)
        conn.execute(f"DELETE FROM memory_vectors WHERE id IN ({marks})", batch)
        cur = conn.execute(f"DELETE FROM memories WHERE id IN ({marks})", batch)
        deleted += cur.rowcount or 0
    conn.commit()
    return deleted


def api_delete_memory(memory_id: str) -> dict:
    for _, path in _scope_databases():
        conn = _connect(path)
        try:
            row = conn.execute(
                "SELECT id FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
            if row is None:
                continue
            _delete_ids(conn, [memory_id])
            return {"ok": True, "deleted": memory_id}
        except sqlite3.Error as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "memory not found"}


def api_update_memory(memory_id: str, data: dict) -> dict:
    updates: list[str] = []
    params: list = []
    if "content" in data:
        updates.append("content = ?")
        params.append(data["content"])
    if "tags" in data:
        updates.append("tags = ?")
        tags = data["tags"]
        params.append(json.dumps(tags) if isinstance(tags, list) else tags)
    if not updates:
        return {"ok": False, "error": "nothing to update"}

    for _, path in _scope_databases():
        conn = _connect(path)
        try:
            row = conn.execute(
                "SELECT id FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
            if row is None:
                continue
            conn.execute(
                f"UPDATE memories SET {', '.join(updates)} WHERE id = ?",
                (*params, memory_id),
            )
            conn.commit()
            return {"ok": True, "updated": memory_id}
        except sqlite3.Error as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "memory not found"}


def _cleanup_matches(rules: list[dict]) -> list[tuple[str, Path, list[str], int]]:
    """Resolve cleanup rules to concrete memory ids, per database.

    Rules are OR-ed: a memory matched by any rule is selected once.
    """
    out: list[tuple[str, Path, list[str], int]] = []

    for name, path in _scope_databases():
        try:
            conn = _connect(path)
            _register_regexp(conn)
        except sqlite3.Error:
            continue

        ids: dict[str, int] = {}
        for rule in rules:
            kind = rule.get("type")
            value = rule.get("value")
            rule_scope = rule.get("scope")
            if rule_scope and rule_scope != name:
                continue

            if kind == "tag":
                where, params = _memory_where(tag=str(value))
            elif kind == "cluster":
                if value is None:
                    continue
                try:
                    where, params = _memory_where(cluster=int(str(value)))
                except ValueError:
                    continue
            elif kind == "scope":
                if value != name:
                    continue
                where, params = "", []
            elif kind == "pattern":
                where, params = _memory_where(pattern=str(value))
            else:
                continue

            try:
                for row in conn.execute(
                    f"SELECT id, LENGTH(content) FROM memories{where}", tuple(params)
                ):
                    ids[row[0]] = row[1] or 0
            except sqlite3.Error:
                continue

        if ids:
            out.append((name, path, list(ids), sum(ids.values())))

    return out


def api_cleanup_preview(rules: list[dict]) -> dict:
    matches = _cleanup_matches(rules)
    total = sum(len(ids) for _, _, ids, _ in matches)
    size = sum(t for _, _, _, t in matches)

    sample: list[dict] = []
    for name, path, ids, _ in matches:
        if len(sample) >= 8:
            break
        try:
            conn = _connect(path)
            marks = ",".join("?" for _ in ids[:8])
            for row in conn.execute(
                f"SELECT id, content, tags, created_at FROM memories WHERE id IN ({marks})",
                ids[:8],
            ):
                d = dict(row)
                d["_scope"] = name
                sample.append(d)
        except sqlite3.Error:
            continue

    return {
        "count": total,
        "size": size,
        "by_scope": [
            {"scope": n, "count": len(ids)} for n, _, ids, _ in matches
        ],
        "sample": sample[:8],
    }


def api_cleanup_execute(rules: list[dict]) -> dict:
    matches = _cleanup_matches(rules)
    deleted = 0
    per_scope = []
    for name, path, ids, _ in matches:
        try:
            n = _delete_ids(_connect(path), ids)
        except sqlite3.Error as e:
            return {"ok": False, "error": str(e), "deleted": deleted}
        deleted += n
        per_scope.append({"scope": name, "deleted": n})
    return {"ok": True, "deleted": deleted, "by_scope": per_scope}


# ─────────────────────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────────────────────

_ALLOWED_HOSTS = re.compile(r"^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", re.IGNORECASE)
_ALLOWED_ORIGINS = re.compile(
    r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", re.IGNORECASE
)


def _int(params: dict, key: str, default: int, cap: int | None = None) -> int:
    try:
        value = int(params.get(key, [default])[0])
    except (TypeError, ValueError):
        return default
    if cap is not None:
        value = min(value, cap)
    return max(value, 0)


def _str(params: dict, key: str) -> str | None:
    value = params.get(key, [None])[0]
    return value or None


class CortexHandler(BaseHTTPRequestHandler):
    server_version = "Cortex"
    protocol_version = "HTTP/1.1"

    # ── guards ────────────────────────────────────────────────

    def _origin_ok(self) -> bool:
        """Reject DNS-rebinding (bad Host) and cross-site writes (bad Origin).

        The API sends no CORS headers, so a foreign page cannot read a
        response; these two checks stop it from reaching the handler at all.
        """
        host = self.headers.get("Host", "")
        if not _ALLOWED_HOSTS.match(host):
            return False
        origin = self.headers.get("Origin")
        if origin and not _ALLOWED_ORIGINS.match(origin):
            return False
        return True

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return {}
        if length <= 0 or length > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # ── verbs ─────────────────────────────────────────────────

    def do_GET(self):
        if not self._origin_ok():
            return self._error(403, "forbidden")
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._route_get(parsed.path, parse_qs(parsed.query))
        else:
            self._static(parsed.path)

    def do_POST(self):
        if not self._origin_ok():
            return self._error(403, "forbidden")
        path = urlparse(self.path).path
        if path == "/api/cleanup/preview":
            self._json(api_cleanup_preview(self._body().get("rules", [])))
        elif path == "/api/cleanup/execute":
            self._json(api_cleanup_execute(self._body().get("rules", [])))
        else:
            self._error(404, "not found")

    def do_PUT(self):
        if not self._origin_ok():
            return self._error(403, "forbidden")
        path = urlparse(self.path).path
        if path.startswith("/api/memory/"):
            memory_id = unquote(path[len("/api/memory/") :])
            self._json(api_update_memory(memory_id, self._body()))
        else:
            self._error(404, "not found")

    def do_DELETE(self):
        if not self._origin_ok():
            return self._error(403, "forbidden")
        path = urlparse(self.path).path
        if path.startswith("/api/memory/"):
            memory_id = unquote(path[len("/api/memory/") :])
            self._json(api_delete_memory(memory_id))
        else:
            self._error(404, "not found")

    # ── routing ───────────────────────────────────────────────

    def _route_get(self, path: str, params: dict):
        scope = _str(params, "scope")

        if path == "/api/overview":
            return self._json(api_overview())

        if path == "/api/clusters":
            return self._json(
                api_clusters(
                    scope,
                    _str(params, "q"),
                    _int(params, "limit", 60, MAX_PAGE_SIZE),
                    _int(params, "offset", 0),
                    params.get("sort", ["size"])[0],
                )
            )

        if path.startswith("/api/clusters/"):
            try:
                cluster_id = int(path[len("/api/clusters/") :])
            except ValueError:
                return self._error(400, "invalid cluster id")
            return self._json(api_cluster_detail(cluster_id, scope))

        if path == "/api/memories":
            cluster_raw = _str(params, "cluster")
            cluster = None
            if cluster_raw is not None:
                try:
                    cluster = int(cluster_raw)
                except ValueError:
                    return self._error(400, "invalid cluster")
            return self._json(
                api_memories(
                    scope,
                    _str(params, "tag"),
                    cluster,
                    _str(params, "q"),
                    params.get("sort", ["recent"])[0],
                    _int(params, "limit", 50, MAX_PAGE_SIZE),
                    _int(params, "offset", 0),
                )
            )

        if path.startswith("/api/memory/"):
            return self._json(api_memory(unquote(path[len("/api/memory/") :])))

        if path == "/api/entity":
            name = _str(params, "name")
            if not name:
                return self._error(400, "name required")
            return self._json(api_entity(name))

        self._error(404, "not found")

    # ── static ────────────────────────────────────────────────

    def _static(self, path: str):
        rel = unquote(path).lstrip("/") or "index.html"
        candidate = (STATIC_DIR / rel).resolve()

        # Containment check: everything served must live under STATIC_DIR.
        if candidate != STATIC_DIR and STATIC_DIR not in candidate.parents:
            candidate = STATIC_DIR / "index.html"
        if not candidate.is_file():
            candidate = STATIC_DIR / "index.html"
        if not candidate.is_file():
            return self._error(404, "dashboard not built")

        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if candidate.parent.name == "assets":
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # ── responses ─────────────────────────────────────────────

    def _json(self, data, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str):
        self._json({"error": message}, status=status)

    def log_message(self, format, *args):
        pass


def run_web(port: int = 37800):
    server = ThreadingHTTPServer(("127.0.0.1", port), CortexHandler)
    server.daemon_threads = True
    print(f"  Cortex Dashboard: http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
