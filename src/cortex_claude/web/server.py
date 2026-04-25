from __future__ import annotations

import json
import mimetypes
import sqlite3
import glob as globmod
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / ".cortex-claude")))
STATIC_DIR = Path(__file__).parent / "static"


def _get_connections() -> list[tuple[str, str]]:
    dbs = []
    global_db = CORTEX_HOME / "global.db"
    if global_db.exists():
        dbs.append(("global", str(global_db)))
    scopes_dir = CORTEX_HOME / "scopes"
    if scopes_dir.is_dir():
        for f in globmod.glob(str(scopes_dir / "*.db")):
            name = Path(f).stem.replace("__", ":")
            dbs.append((name, f))
    return dbs


def _query_all(sql: str, params: tuple = ()) -> list[dict]:
    rows = []
    for scope_name, db_path in _get_connections():
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            for row in conn.execute(sql, params).fetchall():
                d = dict(row)
                d["_scope"] = scope_name
                rows.append(d)
            conn.close()
        except Exception:
            pass
    return rows


def api_stats() -> dict:
    memories = _query_all("SELECT COUNT(*) as c FROM memories")
    facts = _query_all("SELECT COUNT(*) as c FROM facts")
    scopes = _get_connections()

    total_mem = sum(r["c"] for r in memories)
    total_facts = sum(r["c"] for r in facts)
    total_size = sum(os.path.getsize(p) for _, p in scopes if os.path.exists(p))

    scope_details = []
    for name, path in scopes:
        try:
            conn = sqlite3.connect(path)
            mc = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            fc = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            conn.close()
            scope_details.append({
                "name": name,
                "memories": mc,
                "facts": fc,
                "size": os.path.getsize(path),
            })
        except Exception:
            pass

    return {
        "total_memories": total_mem,
        "total_facts": total_facts,
        "total_size": total_size,
        "scopes": scope_details,
    }


def api_memories(scope: str | None = None, limit: int = 100) -> list[dict]:
    rows = _query_all(
        "SELECT id, content, summary, tags, scope, created_at, accessed_at, access_count, decay_score FROM memories ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    if scope:
        rows = [r for r in rows if r["scope"] == scope]
    return rows


def api_graph() -> dict:
    facts = _query_all(
        "SELECT subject, relation, object, confidence, scope FROM facts ORDER BY confidence DESC"
    )

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for f in facts:
        subj = f["subject"]
        obj = f["object"]

        if subj not in nodes:
            nodes[subj] = {"id": subj, "label": subj, "weight": 0}
        nodes[subj]["weight"] += 1

        if obj not in nodes:
            nodes[obj] = {"id": obj, "label": obj, "weight": 0}
        nodes[obj]["weight"] += 1

        edges.append({
            "source": subj,
            "target": obj,
            "label": f["relation"],
            "confidence": f["confidence"],
        })

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def api_entity(name: str) -> dict:
    name_lower = f"%{name.lower()}%"
    facts = _query_all(
        "SELECT subject, relation, object, confidence, scope FROM facts WHERE LOWER(subject) LIKE ? OR LOWER(object) LIKE ? ORDER BY confidence DESC",
        (name_lower, name_lower),
    )
    memories = _query_all(
        "SELECT id, content, tags, scope, created_at, decay_score FROM memories WHERE LOWER(content) LIKE ? ORDER BY created_at DESC LIMIT 10",
        (name_lower,),
    )
    return {"facts": facts, "memories": memories}


def api_search(query: str) -> list[dict]:
    q = f"%{query.lower()}%"
    return _query_all(
        "SELECT id, content, summary, tags, scope, created_at, accessed_at, access_count, decay_score FROM memories WHERE LOWER(content) LIKE ? OR LOWER(tags) LIKE ? ORDER BY decay_score DESC LIMIT 50",
        (q, q),
    )


class CortexHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path.startswith("/api/"):
            self._handle_api(path, params)
        else:
            self._handle_static(path)

    def _handle_api(self, path: str, params: dict):
        if path == "/api/stats":
            self._json(api_stats())
        elif path == "/api/memories":
            scope = params.get("scope", [None])[0]
            self._json(api_memories(scope=scope))
        elif path == "/api/graph":
            self._json(api_graph())
        elif path == "/api/entity":
            name = params.get("name", [""])[0]
            self._json(api_entity(name))
        elif path == "/api/search":
            query = params.get("q", [""])[0]
            self._json(api_search(query))
        else:
            self._not_found()

    def _handle_static(self, path: str):
        if path == "/" or path == "":
            path = "/index.html"

        file_path = STATIC_DIR / path.lstrip("/")

        if not file_path.exists() or not file_path.is_file():
            file_path = STATIC_DIR / "index.html"

        if not file_path.exists():
            self._not_found()
            return

        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        body = file_path.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if "assets/" in str(file_path):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self):
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def run_web(port: int = 37800):
    server = HTTPServer(("127.0.0.1", port), CortexHandler)
    print(f"  Cortex Dashboard: http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
