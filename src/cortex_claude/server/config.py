from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CortexConfig:
    base_path: Path = field(default_factory=lambda: Path.home() / ".cortex-claude")
    default_max_tokens: int = 200
    embedding_model: str = "all-MiniLM-L6-v2"
    scope_mappings: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, base_path: Path | None = None) -> CortexConfig:
        path = base_path or Path.home() / ".cortex-claude"
        config_file = path / "config.json"

        config = cls(base_path=path)

        if config_file.exists():
            with open(config_file) as f:
                raw = json.load(f)

            config.default_max_tokens = raw.get("recall", {}).get(
                "default_max_tokens", 200
            )
            config.embedding_model = raw.get("embeddings", {}).get(
                "model", "all-MiniLM-L6-v2"
            )
            config.scope_mappings = raw.get("scopes", {}).get("mappings", {})

        return config
