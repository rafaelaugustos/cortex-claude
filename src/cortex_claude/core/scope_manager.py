from __future__ import annotations

import json
from pathlib import Path

from cortex_claude.models.scope import ScopeConfig


class ScopeManager:
    def __init__(self, base_path: Path):
        self._base_path = base_path
        self._config = self._load_config()

    def _load_config(self) -> ScopeConfig:
        config_path = self._base_path / "config.json"
        if not config_path.exists():
            return ScopeConfig()

        with open(config_path) as f:
            raw = json.load(f)

        scopes_raw = raw.get("scopes", {})
        return ScopeConfig(
            mappings=scopes_raw.get("mappings", {}),
            default=scopes_raw.get("default", "global"),
            search_order=scopes_raw.get("search_order", "project_first"),
        )

    def resolve(self, cwd: str) -> list[str]:
        cwd_path = Path(cwd).resolve()
        scopes: list[str] = []

        for path_str, scope_name in self._config.mappings.items():
            mapped_path = Path(path_str).resolve()
            if cwd_path == mapped_path or mapped_path in cwd_path.parents:
                scopes.append(scope_name)

        if "global" not in scopes:
            scopes.append("global")

        return scopes

    def get_write_scope(self, cwd: str) -> str:
        scopes = self.resolve(cwd)
        return scopes[0]

    def reload(self) -> None:
        self._config = self._load_config()
