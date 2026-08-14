from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_claude.setup import PRE_TOOL_USE_HOOK


@pytest.fixture(scope="module")
def hook_script(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("hooks")
    script = d / "pre-tool-use.sh"
    script.write_text(PRE_TOOL_USE_HOOK)
    script.chmod(0o755)
    return script


def run_hook(hook_script: Path, payload: dict) -> str:
    result = subprocess.run(
        [str(hook_script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    return result.stdout.strip()


class TestPreToolUseHook:
    def test_rewrites_git_status(self, hook_script: Path):
        out = run_hook(hook_script, {
            "tool_name": "Bash",
            "tool_input": {"command": "git status", "timeout": 120000},
        })
        data = json.loads(out)
        updated = data["hookSpecificOutput"]["updatedInput"]
        assert updated["command"] == "git status --short --branch"
        assert updated["timeout"] == 120000  # other fields preserved
        assert data["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_rewrites_git_log(self, hook_script: Path):
        out = run_hook(hook_script, {
            "tool_name": "Bash",
            "tool_input": {"command": "git log", "description": "check history"},
        })
        data = json.loads(out)
        updated = data["hookSpecificOutput"]["updatedInput"]
        assert updated["command"] == "git log --oneline -n 20"
        assert updated["description"] == "check history"

    def test_does_not_rewrite_command_with_existing_flags(self, hook_script: Path):
        out = run_hook(hook_script, {
            "tool_name": "Bash",
            "tool_input": {"command": "git status --short"},
        })
        assert out == ""

    def test_does_not_rewrite_unknown_command(self, hook_script: Path):
        out = run_hook(hook_script, {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        })
        assert out == ""

    def test_ignores_non_bash_tools(self, hook_script: Path):
        out = run_hook(hook_script, {
            "tool_name": "Read",
            "tool_input": {"file_path": "/a.py"},
        })
        assert out == ""

    def test_malformed_json_does_not_crash(self, hook_script: Path):
        result = subprocess.run(
            [str(hook_script)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_empty_command_does_not_crash(self, hook_script: Path):
        out = run_hook(hook_script, {
            "tool_name": "Bash",
            "tool_input": {},
        })
        assert out == ""
