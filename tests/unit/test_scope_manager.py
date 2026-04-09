import json
from pathlib import Path

from cortex_claude.core.scope_manager import ScopeManager


def test_resolve_no_config(tmp_path: Path):
    manager = ScopeManager(base_path=tmp_path)
    scopes = manager.resolve("/some/random/path")
    assert scopes == ["global"]


def test_resolve_with_mapping(tmp_path: Path):
    config = {
        "scopes": {
            "mappings": {
                "/projects/api": "project:api",
            }
        }
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))

    manager = ScopeManager(base_path=tmp_path)
    scopes = manager.resolve("/projects/api")
    assert scopes == ["project:api", "global"]


def test_resolve_subdirectory_matches(tmp_path: Path):
    config = {
        "scopes": {
            "mappings": {
                "/projects/api": "project:api",
            }
        }
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))

    manager = ScopeManager(base_path=tmp_path)
    scopes = manager.resolve("/projects/api/src/controllers")
    assert "project:api" in scopes
    assert "global" in scopes


def test_get_write_scope_prefers_project(tmp_path: Path):
    config = {
        "scopes": {
            "mappings": {
                "/projects/api": "project:api",
            }
        }
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))

    manager = ScopeManager(base_path=tmp_path)
    assert manager.get_write_scope("/projects/api") == "project:api"


def test_get_write_scope_falls_back_to_global(tmp_path: Path):
    manager = ScopeManager(base_path=tmp_path)
    assert manager.get_write_scope("/unknown/path") == "global"
