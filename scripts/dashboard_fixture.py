"""Serve the real dashboard/API against disposable data for browser verification."""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from cortex_claude.learning.extraction import Observation
from cortex_claude.learning.store import LearningStore
from cortex_claude.learning.tasks import save_task
from cortex_claude.storage.database import StorageManager
from cortex_claude.web import server as web


def seed(home: Path) -> None:
    (home / "config.json").write_text('{"learning":{"semantic_enabled":false}}')
    project = home / 'example-project'
    project.mkdir()
    (project / 'package.json').write_text(json.dumps({'name': 'Orders demo', 'description': 'Organiza pedidos', 'dependencies': {'vue': '3'}, 'scripts': {'test': 'vitest'}}))
    (project / 'README.md').write_text('# Orders\nThe parser normalizes order values.\n')
    (project / 'parser.py').write_text('def normalize(value):\n    return value.strip()\n\ndef parse(value):\n    return normalize(value)\n')
    with LearningStore(home) as store:
        from cortex_claude.learning.projects import refresh_project, add_note
        refresh_project(store, str(project))
        add_note(store, str(project), 'architecture', 'O parser normaliza os valores dos pedidos.', ['README.md'])
        store.observe(Observation("Prefiro funções pequenas e com uma responsabilidade", "code.size", "personal", "code", explicit=True), "/example/api", "one")
        store.observe(Observation("Use pytest para testes Python", "python.tests", "personal", "python tests"), "/example/api", "two")
        store.observe(Observation("Use unittest para testes Python", "python.tests", "personal", "python tests"), "/example/api", "three")
        save_task(store, "/example/api", "one", title="Revisar parser de configuração", summary="Conversão extraída; falta integrar os consumidores", next_step="Integrar o parser e rodar os testes", decisions=["Preservar a API pública"], pending=["Atualizar worker", "Verificar valores vazios"])
    storage = StorageManager(home)
    now = int(time.time() * 1000)
    for scope in ("global", "project:example"):
        conn = storage.get_database(scope)
        with conn:
            conn.execute("INSERT INTO clusters(id,scope,label,member_count,updated_at) VALUES (1,?,?,?,?)", (scope, "Arquitetura da aplicação", 25, now))
            for i in range(25):
                memory_id = f"{scope}-{i}"
                conn.execute("INSERT INTO memories(id,content,tags,scope,created_at,updated_at,accessed_at,cluster_id) VALUES (?,?,?,?,?,?,?,1)", (memory_id, f"Decisão {i}: a aplicação usa PostgreSQL para persistência.", json.dumps(["rascunho" if i == 0 else "arquitetura"]), scope, now + i * 10 + (1 if scope == "global" else 2), now, now))
                conn.execute("INSERT INTO facts(id,subject,relation,object,source_memory_id,scope,created_at) VALUES (?,?,?,?,?,?,?)", (f"fact:{memory_id}", "aplicação", "usa", "PostgreSQL", memory_id, scope, now))
    conn = storage.get_database('global')
    with conn:
        conn.execute("INSERT INTO execution_history(id,content,tags,scope,created_at,updated_at,accessed_at) VALUES ('old-grep','Command: grep old-invoice Result: stdout','[\"auto-capture\"]','global',?,?,?)", (now,now,now))
    storage.close_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=37813)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cortex-dashboard-") as directory:
        home = Path(directory)
        seed(home)
        web.CORTEX_HOME = home
        server = web.ThreadingHTTPServer(("127.0.0.1", args.port), web.CortexHandler)
        try:
            print(f"Disposable dashboard at http://127.0.0.1:{args.port}", flush=True)
            server.serve_forever()
        finally:
            server.server_close()
