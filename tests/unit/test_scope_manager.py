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


def test_auto_project_scope_derives_from_dir_name(tmp_path: Path):
    manager = ScopeManager(base_path=tmp_path)
    project_dir = tmp_path / "my-cool-app"
    project_dir.mkdir()
    assert manager.auto_project_scope(str(project_dir)) == "project:my-cool-app"


def test_auto_project_scope_normalizes_special_chars(tmp_path: Path):
    manager = ScopeManager(base_path=tmp_path)
    project_dir = tmp_path / "My Cool_App!!2.0"
    project_dir.mkdir()
    assert manager.auto_project_scope(str(project_dir)) == "project:my-cool-app-2-0"


def test_auto_project_scope_respects_explicit_mapping(tmp_path: Path):
    config = {
        "scopes": {
            "mappings": {
                str(tmp_path / "projects" / "api"): "project:api",
            }
        }
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))

    manager = ScopeManager(base_path=tmp_path)
    project_dir = tmp_path / "projects" / "api"
    project_dir.mkdir(parents=True)
    assert manager.auto_project_scope(str(project_dir)) == "project:api"


def test_auto_project_scope_does_not_affect_get_write_scope(tmp_path: Path):
    """auto_project_scope is isolated to code indexing — get_write_scope
    (used by save/recall/auto-capture) must keep falling back to global."""
    manager = ScopeManager(base_path=tmp_path)
    project_dir = tmp_path / "some-app"
    project_dir.mkdir()
    assert manager.auto_project_scope(str(project_dir)) == "project:some-app"
    assert manager.get_write_scope(str(project_dir)) == "global"
