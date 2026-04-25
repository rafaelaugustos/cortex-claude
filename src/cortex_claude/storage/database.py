from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

from cortex_claude.storage.migrations import initialize_schema


class StorageManager:
    def __init__(self, base_path: Path | None = None, embedding_dim: int = 384):
        self._base_path = base_path or Path.home() / ".cortex-claude"
        self._embedding_dim = embedding_dim
        self._connections: dict[str, sqlite3.Connection] = {}
        self._base_path.mkdir(parents=True, exist_ok=True)
        (self._base_path / "scopes").mkdir(exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._base_path

    def _scope_to_path(self, scope: str) -> Path:
        if scope == "global":
            return self._base_path / "global.db"
        safe_name = scope.replace(":", "__")
        return self._base_path / "scopes" / f"{safe_name}.db"

    def get_database(self, scope: str) -> sqlite3.Connection:
        if scope in self._connections:
            return self._connections[scope]

        db_path = self._scope_to_path(scope)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        initialize_schema(conn, embedding_dim=self._embedding_dim)

        self._connections[scope] = conn
        return conn

    def list_scopes(self) -> list[str]:
        scopes: list[str] = []

        global_db = self._base_path / "global.db"
        if global_db.exists():
            scopes.append("global")

        scopes_dir = self._base_path / "scopes"
        if scopes_dir.exists():
            for db_file in scopes_dir.glob("*.db"):
                scope_name = db_file.stem.replace("__", ":")
                scopes.append(scope_name)

        return sorted(scopes)

    def get_database_path(self, scope: str) -> Path:
        return self._scope_to_path(scope)

    def delete_scope(self, scope: str) -> None:
        if scope in self._connections:
            self._connections[scope].close()
            del self._connections[scope]

        db_path = self._scope_to_path(scope)
        if db_path.exists():
            db_path.unlink()

    def vacuum(self, scope: str) -> None:
        conn = self.get_database(scope)
        conn.execute("VACUUM")

    def close_all(self) -> None:
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
