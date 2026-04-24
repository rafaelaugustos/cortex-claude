import json
from pathlib import Path

from cortex_claude.server.config import CortexConfig


def test_default_config():
    config = CortexConfig()
    assert config.default_max_tokens == 200
    assert config.decay_lambda == 0.05
    assert config.dedup_similarity_threshold == 0.92
    assert config.fact_min_confidence == 0.5


def test_load_from_file(tmp_path: Path):
    config_data = {
        "recall": {"default_max_tokens": 500},
        "decay": {"lambda": 0.1, "min_score": 0.05},
        "deduplication": {"similarity_threshold": 0.85},
        "facts": {"min_confidence": 0.7},
        "scopes": {
            "mappings": {"/projects/api": "project:api"},
            "default": "global",
        },
    }

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))

    config = CortexConfig.load(tmp_path)
    assert config.default_max_tokens == 500
    assert config.decay_lambda == 0.1
    assert config.decay_min_score == 0.05
    assert config.dedup_similarity_threshold == 0.85
    assert config.fact_min_confidence == 0.7
    assert config.scope_mappings == {"/projects/api": "project:api"}


def test_load_missing_file(tmp_path: Path):
    config = CortexConfig.load(tmp_path)
    assert config.default_max_tokens == 200


def test_load_partial_config(tmp_path: Path):
    config_data = {"decay": {"lambda": 0.2}}
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))

    config = CortexConfig.load(tmp_path)
    assert config.decay_lambda == 0.2
    assert config.default_max_tokens == 200
