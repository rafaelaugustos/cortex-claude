import json
import os
import subprocess
import sys

from cortex_claude import setup


def test_setup_preserves_other_hooks_and_is_idempotent():
    command = str(setup.HOOKS_DIR / "session-start.sh")
    hooks = {"SessionStart": [{"matcher": "startup", "hooks": [
        {"type": "command", "command": "another-tool start"},
        {"type": "command", "command": command},
    ]}], "Stop": [{"hooks": [{"type": "command", "command": "unrelated"}]}]}
    entries = {"SessionStart": {"type": "command", "command": command}}
    setup.merge_cortex_hooks(hooks, entries)
    once = json.dumps(hooks, sort_keys=True)
    setup.merge_cortex_hooks(hooks, entries)
    assert json.dumps(hooks, sort_keys=True) == once
    assert hooks["SessionStart"][0]["matcher"] == "startup"
    assert hooks["SessionStart"][0]["hooks"][0]["command"] == "another-tool start"
    assert "Stop" in hooks


def test_instruction_upgrade_preserves_user_content():
    original = "# My instructions\nKeep this.\n\n" + setup.LEGACY_CLAUDE_MD_CONTENT + "\n# Other notes\nKeep these too.\n"
    updated = setup.update_memory_instructions(original)
    assert "Keep this." in updated and "Keep these too." in updated
    assert updated.count("<!-- cortex-memory:start -->") == 1
    assert "Before saying" not in updated
    assert setup.update_memory_instructions(updated) == updated


def test_real_prompt_hook_runs_without_loading_ml_or_daemon(tmp_path):
    env = {**os.environ, "CORTEX_HOME": str(tmp_path)}
    result = subprocess.run([sys.executable, "-m", "cortex_claude", "hook", "UserPromptSubmit"],
                            input=json.dumps({"cwd": "/a", "session_id": "s", "prompt": "Sempre prefiro funções pequenas"}),
                            text=True, capture_output=True, env=env, timeout=5)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    check = subprocess.run([sys.executable, "-c", "import sys; import cortex_claude.hooks; assert 'torch' not in sys.modules; assert 'spacy' not in sys.modules"], capture_output=True, timeout=5)
    assert check.returncode == 0, check.stderr


def test_real_prompt_hook_injects_compact_context(tmp_path):
    from cortex_claude.learning.store import LearningStore
    from cortex_claude.learning.extraction import Observation
    with LearningStore(tmp_path) as store:
        store.observe(Observation("Prefiro funções pequenas", "code.function-size", "personal", "code", True), "/a", "first")
    env = {**os.environ, "CORTEX_HOME": str(tmp_path)}
    result = subprocess.run([sys.executable, "-m", "cortex_claude", "hook", "UserPromptSubmit"],
                            input=json.dumps({"cwd": "/b", "session_id": "s", "prompt": "Implement an endpoint"}),
                            text=True, capture_output=True, env=env, timeout=5)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "funções pequenas" in output["hookSpecificOutput"]["additionalContext"]


def test_malformed_hook_input_never_blocks(tmp_path):
    result = subprocess.run([sys.executable, "-m", "cortex_claude", "hook", "UserPromptSubmit"],
                            input="invalid json", text=True, capture_output=True,
                            env={**os.environ, "CORTEX_HOME": str(tmp_path)}, timeout=5)
    assert result.returncode == 0
    assert "systemMessage" in json.loads(result.stdout)
    assert (tmp_path / "hook-error.log").exists()


def test_full_hook_install_preserves_user_configuration(tmp_path, monkeypatch):
    paths = {
        "CORTEX_HOME": tmp_path / "data",
        "HOOKS_DIR": tmp_path / "data/hooks",
        "CLAUDE_CONFIG": tmp_path / "claude.json",
        "CLAUDE_SETTINGS": tmp_path / "claude/settings.json",
        "CLAUDE_MD": tmp_path / "claude/CLAUDE.md",
    }
    for key, path in paths.items():
        monkeypatch.setattr(setup, key, path)
    paths["CLAUDE_SETTINGS"].parent.mkdir()
    paths["CLAUDE_SETTINGS"].write_text(json.dumps({"theme": "dark", "hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": "my-stop-hook"}]}],
        "SessionStart": [{"hooks": [{"type": "command", "command": "my-start-hook"}]}],
    }}))
    paths["CLAUDE_CONFIG"].write_text(json.dumps({"mcpServers": {"other": {"command": "other"}, "cortex": {"env": {"EXISTING_OPTION": "keep"}}}}))
    paths["CLAUDE_MD"].write_text("# My instructions\nKeep this text.\n")
    setup.run_setup(hooks_only=True)
    once = paths["CLAUDE_SETTINGS"].read_text()
    setup.run_setup(hooks_only=True)
    assert paths["CLAUDE_SETTINGS"].read_text() == once
    settings = json.loads(once)
    assert settings["theme"] == "dark"
    assert "Stop" in settings["hooks"]
    assert "UserPromptSubmit" in settings["hooks"]
    assert settings["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "my-start-hook"
    assert "Keep this text." in paths["CLAUDE_MD"].read_text()
    assert paths["CLAUDE_MD"].read_text().count("<!-- cortex-memory:start -->") == 1
    mcp = json.loads(paths["CLAUDE_CONFIG"].read_text())
    assert "other" in mcp["mcpServers"]
    assert mcp["mcpServers"]["cortex"]["env"]["EXISTING_OPTION"] == "keep"
    assert list(tmp_path.glob("claude.json.cortex-backup-*"))


def test_corrupt_configuration_is_not_replaced(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"learning":{"confirmations":0}}')
    from cortex_claude.learning.config import LearningConfig
    import pytest
    with pytest.raises(ValueError, match="confirmations"):
        LearningConfig.load(tmp_path)
