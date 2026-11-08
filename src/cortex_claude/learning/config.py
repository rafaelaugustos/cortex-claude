from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LearningConfig:
    enabled: bool = True
    confirmations: int = 3
    min_contexts: int = 2
    max_context_tokens: int = 180
    max_session_tokens: int = 600
    max_lesson_tokens: int = 80
    max_items: int = 5
    capture_tools: bool = False
    semantic_enabled: bool = True
    semantic_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    semantic_merge_threshold: float = 0.88
    semantic_recall_threshold: float = 0.65
    semantic_timeout_ms: int = 250
    max_detail_tokens: int = 600
    experience_ttl_days: int = 90
    measure_usage: bool = True
    project_memory: bool = True

    @classmethod
    def load(cls, home: Path) -> LearningConfig:
        config = cls()
        path = home / "config.json"
        if not path.exists():
            return config
        raw = json.loads(path.read_text()).get("learning", {})
        if not isinstance(raw, dict):
            raise ValueError("learning must be an object")
        for field in ("enabled", "capture_tools", "semantic_enabled", "measure_usage", "project_memory"):
            if field in raw:
                if not isinstance(raw[field], bool):
                    raise ValueError(f"learning.{field} must be a boolean")
                setattr(config, field, raw[field])
        for field, upper in {
            "confirmations": 100, "min_contexts": 100,
            "max_context_tokens": 2000, "max_session_tokens": 20000,
            "max_lesson_tokens": 300, "max_items": 20,
            "semantic_timeout_ms": 1000, "max_detail_tokens": 4000,
            "experience_ttl_days": 3650,
        }.items():
            if field in raw:
                value = raw[field]
                if type(value) is not int or not 1 <= value <= upper:
                    raise ValueError(f"learning.{field} must be between 1 and {upper}")
                setattr(config, field, value)
        for field in ("semantic_merge_threshold", "semantic_recall_threshold"):
            if field in raw:
                value = raw[field]
                if type(value) not in (int, float) or not 0.5 <= value <= 1:
                    raise ValueError(f"learning.{field} must be between 0.5 and 1")
                setattr(config, field, float(value))
        if "semantic_model" in raw:
            if not isinstance(raw["semantic_model"], str) or not raw["semantic_model"].strip():
                raise ValueError("learning.semantic_model must be a model name")
            config.semantic_model = raw["semantic_model"].strip()
        return config
