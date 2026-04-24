from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CortexConfig:
    base_path: Path = field(default_factory=lambda: Path.home() / ".cortex-claude")

    # Storage
    max_db_size_mb: int = 500

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_batch_size: int = 32

    # Recall
    default_max_tokens: int = 200
    default_depth: str = "auto"
    sufficiency_coverage_threshold: float = 0.7
    sufficiency_confidence_threshold: float = 0.6

    # Facts
    fact_extraction_method: str = "local"
    fact_min_confidence: float = 0.5

    # Decay
    decay_lambda: float = 0.05
    decay_recalculate_interval_hours: int = 6
    decay_min_score: float = 0.01

    # Deduplication
    dedup_similarity_threshold: float = 0.92
    dedup_merge_strategy: str = "append"

    # Scopes
    scope_mappings: dict[str, str] = field(default_factory=dict)
    scope_default: str = "global"
    scope_search_order: str = "project_first"

    @classmethod
    def load(cls, base_path: Path | None = None) -> CortexConfig:
        path = base_path or Path.home() / ".cortex-claude"
        config_file = path / "config.json"

        config = cls(base_path=path)

        if not config_file.exists():
            return config

        with open(config_file) as f:
            raw = json.load(f)

        storage = raw.get("storage", {})
        config.max_db_size_mb = storage.get("max_db_size_mb", config.max_db_size_mb)

        embeddings = raw.get("embeddings", {})
        config.embedding_model = embeddings.get("model", config.embedding_model)
        config.embedding_batch_size = embeddings.get("batch_size", config.embedding_batch_size)

        recall = raw.get("recall", {})
        config.default_max_tokens = recall.get("default_max_tokens", config.default_max_tokens)
        config.default_depth = recall.get("default_depth", config.default_depth)
        sufficiency = recall.get("sufficiency", {})
        config.sufficiency_coverage_threshold = sufficiency.get(
            "coverage_threshold", config.sufficiency_coverage_threshold
        )
        config.sufficiency_confidence_threshold = sufficiency.get(
            "confidence_threshold", config.sufficiency_confidence_threshold
        )

        facts = raw.get("facts", {})
        config.fact_extraction_method = facts.get("extraction_method", config.fact_extraction_method)
        config.fact_min_confidence = facts.get("min_confidence", config.fact_min_confidence)

        decay = raw.get("decay", {})
        config.decay_lambda = decay.get("lambda", config.decay_lambda)
        config.decay_recalculate_interval_hours = decay.get(
            "recalculate_interval_hours", config.decay_recalculate_interval_hours
        )
        config.decay_min_score = decay.get("min_score", config.decay_min_score)

        dedup = raw.get("deduplication", {})
        config.dedup_similarity_threshold = dedup.get(
            "similarity_threshold", config.dedup_similarity_threshold
        )
        config.dedup_merge_strategy = dedup.get("merge_strategy", config.dedup_merge_strategy)

        scopes = raw.get("scopes", {})
        config.scope_mappings = scopes.get("mappings", config.scope_mappings)
        config.scope_default = scopes.get("default", config.scope_default)
        config.scope_search_order = scopes.get("search_order", config.scope_search_order)

        return config
