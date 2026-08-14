from __future__ import annotations

import json
import re
from pathlib import Path

from cortex_claude.models.scope import ScopeConfig

_SLUG_RE = re.compile(r"[^a-z0-9-]+")
_DASH_COLLAPSE_RE = re.compile(r"-+")


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

    def auto_project_scope(self, cwd: str) -> str:
        """Scope to use for whole-project code indexing when no scope is
        explicitly mapped for `cwd`.

        Unlike `get_write_scope` (used by save/recall/auto-capture, which
        intentionally falls back to "global"), this derives a
        `project:<dir-name>` scope from the directory name so that
        full-project code scans for different, unconfigured projects don't
        all land in the same "global" graph. Only affects code indexing —
        does not persist a mapping to config.json and does not change
        `get_write_scope`'s behavior.
        """
        scopes = self.resolve(cwd)
        explicit = scopes[0]
        if explicit != "global":
            return explicit

        name = Path(cwd).resolve().name
        slug = _SLUG_RE.sub("-", name.lower())
        slug = _DASH_COLLAPSE_RE.sub("-", slug).strip("-")
        if not slug:
            return "global"
        return f"project:{slug}"

    def reload(self) -> None:
        self._config = self._load_config()
