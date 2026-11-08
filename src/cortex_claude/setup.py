from __future__ import annotations

import importlib.util
import json
import os
import shutil
import shlex
import stat
import subprocess
import sys
from pathlib import Path

CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / ".cortex-claude"))).expanduser()
CLAUDE_CONFIG = Path.home() / ".claude.json"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
HOOKS_DIR = CORTEX_HOME / "hooks"

LEGACY_CLAUDE_MD_CONTENT = """# Cortex Memory

You have access to **Cortex**, a persistent memory system with a knowledge graph and code graph. Use it.

## Rules

1. **Before reading a code file to find a function** — try `cortex_code(symbol)` first. Returns where it's defined, what it calls, who calls it, and which memories mention it. ~50-150 tokens vs ~1000+ to read the file.
2. **Before saying "I don't know"** — always check Cortex first with `cortex_recall` or `cortex_facts`.
3. **Save important context** — when you learn something significant about the project, user preferences, architecture decisions, or bugs, save it with `cortex_save`.
4. **Use facts for quick lookups** — `cortex_facts` returns structured triplets at minimal token cost. Use it for "what does X use?" type questions.
5. **Use traverse for exploration** — `cortex_traverse` follows entity connections. Use it to discover related information you didn't know to ask about. Accepts `start="cluster:42"` to begin from a sub-graph.
6. **Use clusters for top-down navigation** — `cortex_clusters` lists semantic sub-graphs of your memory so you can see what topics exist before drilling in.
7. **Respect privacy** — never save content wrapped in `<private>...</private>` tags. Cortex strips these automatically, but be mindful of sensitive data.

## Available Tools

| Tool | When to use |
|------|------------|
| `cortex_code` | Look up a code symbol: definition, callers, callees, mentions. Cheap alternative to reading a file. |
| `cortex_index_code` | Index a file or directory into the code graph (Python, JS/TS, Go, Java, Swift, Kotlin). |
| `cortex_save` | Save information worth remembering across sessions |
| `cortex_recall` | Search memories by meaning (semantic + keyword) |
| `cortex_facts` | Quick structured lookup from knowledge graph |
| `cortex_traverse` | Explore connections: start from entity or `cluster:<id>` |
| `cortex_clusters` | List or rebuild sub-graphs of memory (auto-formed by similarity) |
| `cortex_forget` | Delete outdated or wrong memories (dry-run first) |
| `cortex_scopes` | Manage memory scopes (list, create, link) |
| `cortex_status` | Check memory stats (count, size, scopes) |

## What to Save

- Architecture decisions and their rationale
- User preferences and conventions
- Bug context and root causes
- Project-specific terminology
- Environment and deployment details
- API contracts and integrations

## What NOT to Save

- Code that's already in files (it's in the repo — use `cortex_code` instead)
- Temporary debugging output
- Content marked with `<private>` tags
- Information that changes every commit (use git for that)
"""

CLAUDE_MD_CONTENT = """<!-- cortex-memory:start -->
# Cortex Memory

Memory arrives automatically. Current instructions take precedence; do not recall supplied context. Reading/reuse is never evidence. Never save <private> content.

Use cortex_learn for compact preferences/corrections with stable topics. explicit=true only for standing user instructions; project facts use applicability="context". conditions and file dependencies constrain reuse.

After a reusable fix, record experience with situation/cause/solution. Link verification_id (status lists receipts) only when that test verifies the fix. Unverified episodes stay hypotheses. Report passed/failed outcomes after new applications; failures suspend reuse. Read lesson details only when needed.

Use native Read directly before Edit if the editor requires its own receipt. Use cortex_read for bounded/repeated inspection without duplicate editor reads; mode="full" recovers a missing base, and more indicates remaining lines.

Use cortex_task at meaningful handoffs, not after each tool call: save objective/state, decisions, pending work, next_step and dependencies within 240 tokens. List/resume before restarting; verify files when needs_review=true. Updates/completion require expected_revision. Mark finished tasks complete.
Automatic checkpoints preserve partial requests, changed paths and the assistant's last report. They are unverified; inspect current files before continuing and never infer completion from them. Failed memory saves are not confirmed persistence: report the failure. The dashboard's Health view shows durable pending operations and verified local backups.

For observed utility, cortex_learn action="feedback" accepts lesson_id, assessment=useful/irrelevant/corrected and query. It changes usefulness, never confirmations. Conflicts await dashboard review.

Use cortex_code for symbols, cortex_recall for missing archived context, cortex_save for reference material.
Use cortex_project read before exploring a repository; refresh if missing/stale. Read relevant docs and entrypoints, then note purpose, architecture, conventions and decisions with supporting source files. Declared stack alone is not architectural understanding. Never save raw tool transcripts; save what was learned and why.
<!-- cortex-memory:end -->
"""


def _hook_launcher(event: str) -> str:
    return "#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -m cortex_claude hook " + shlex.quote(event) + "\n"


SESSION_START_HOOK = _hook_launcher("SessionStart")
USER_PROMPT_HOOK = _hook_launcher("UserPromptSubmit")
STOP_HOOK = _hook_launcher("Stop")
FAILURE_HOOK = _hook_launcher("PostToolUseFailure")


PRE_TOOL_USE_HOOK = '''#!/bin/bash
# Cortex Claude — PreToolUse hook (Bash only)
# Rewrites a small set of known-verbose git/ls commands to compact,
# information-equivalent flags before execution, to reduce the tokens the
# agent has to read. This only rewrites *exact known patterns* it recognizes
# as safe (no flags that would change semantics) — anything else passes
# through unmodified. It never blocks or denies; worst case is a no-op.

INPUT=$(cat)

python3 -c "
import json, sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if data.get('tool_name') != 'Bash':
    sys.exit(0)

ti = data.get('tool_input', {}) or {}
cmd = ti.get('command', '')
if not isinstance(cmd, str):
    sys.exit(0)

stripped = cmd.strip()

# (exact command or bare prefix with no args) -> compact replacement.
# Conservative on purpose: only rewrite when we recognize the *whole*
# command, so we never clobber flags the caller already chose.
REWRITES = {
    'git status': 'git status --short --branch',
    'git log': 'git log --oneline -n 20',
    'git branch': 'git branch --list',
}

new_cmd = REWRITES.get(stripped)
if new_cmd is None or new_cmd == stripped:
    sys.exit(0)

updated_input = dict(ti)
updated_input['command'] = new_cmd

print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'updatedInput': updated_input,
    }
}))
" <<< "$INPUT"

exit 0
'''

POST_TOOL_USE_HOOK = _hook_launcher("PostToolUse")


def _print(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  [ok] {msg}")


def _skip(msg: str) -> None:
    print(f"  [skip] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _pip_install_cmd() -> tuple[list[str], dict[str, str] | None]:
    """Build an install command (and env, if any) that works whether or not
    `pip` is present.

    spaCy's own `spacy download` picks between `python -m pip install` and
    `uv pip install` internally (see spacy.cli.download._get_pip_install_cmd),
    but its fallback assumes an "active" venv that `uv` recognizes — which
    isn't true for `uv tool install`-managed environments (or plain `uv
    venv`/`uv sync` ones without pip bootstrapped), producing a confusing
    "No virtual environment found" error. We build the command explicitly
    instead: prefer real pip if importable, otherwise call `uv pip install`
    scoped to this exact interpreter via `--python sys.executable`.

    Even with an explicit `--python <path>`, `uv` still scans PATH to
    validate/compare interpreters, and can fail on unrelated broken shims
    from other Python version managers (pyenv, asdf, etc. — a broken
    `~/.pyenv/shims/python` is enough to make `uv pip install` fail with a
    confusing interpreter-query error, even though it's not the interpreter
    we asked for). Overriding just PATH on top of an inherited `os.environ`
    isn't enough: some shells/tools (e.g. gvm) stash a full copy of an old
    PATH in a *different* env var (observed: `GVM_PATH_BACKUP`), and uv (or
    the shell it spawns) can still pick that up. We work around this with a
    genuinely minimal environment — not `os.environ` with PATH overridden —
    containing only PATH (uv's directory + the target interpreter's
    directory) and HOME (uv needs it to locate its cache/config).
    """
    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip", "install"], None

    uv_path = shutil.which("uv")
    if uv_path:
        minimal_path = os.pathsep.join(
            dict.fromkeys([os.path.dirname(uv_path), os.path.dirname(sys.executable)])
        )
        env = {"PATH": minimal_path}
        if "HOME" in os.environ:
            env["HOME"] = os.environ["HOME"]
        return [uv_path, "pip", "install", "--python", sys.executable], env

    raise RuntimeError("neither pip nor uv is available to install packages")


def _download_spacy_model(model_name: str = "en_core_web_sm") -> None:
    """Download and install a spaCy pipeline package without relying on
    `spacy download`'s own pip/uv fallback (see _pip_install_cmd)."""
    from spacy.about import __download_url__
    from spacy.cli.download import get_compatibility, get_model_filename, get_version

    compatibility = get_compatibility()
    version = get_version(model_name, compatibility)
    filename = get_model_filename(model_name, version)
    base_url = __download_url__ if __download_url__.endswith("/") else __download_url__ + "/"
    download_url = base_url + filename

    cmd, env = _pip_install_cmd()
    proc = subprocess.run(cmd + [download_url], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-500:] or "spacy model install failed")


def backup_file(path: Path) -> None:
    if path.exists():
        import time
        backup = path.with_name(path.name + f".cortex-backup-{time.time_ns()}")
        shutil.copy2(path, backup)


def write_json_safely(path: Path, data: dict) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_file(path)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as temp:
        json.dump(data, temp, indent=2)
        temp.write("\n")
    Path(temp.name).replace(path)


def merge_cortex_hooks(hooks: dict, entries: dict) -> None:
    known = {str(HOOKS_DIR / name) for name in (
        "session-start.sh", "pre-tool-use.sh", "post-tool-use.sh", "user-prompt-submit.sh", "stop.sh", "post-tool-failure.sh", "pre-compact.sh", "session-end.sh",
    )}
    for event in set(entries) | {"PreToolUse"}:
        preserved = []
        for group in hooks.get(event, []):
            others = [h for h in group.get("hooks", []) if h.get("command") not in known]
            if others:
                preserved.append({**group, "hooks": others})
        if event in entries:
            preserved.append({"hooks": [entries[event]]})
        if preserved:
            hooks[event] = preserved
        else:
            hooks.pop(event, None)


def update_memory_instructions(existing: str) -> str:
    start, end = "<!-- cortex-memory:start -->", "<!-- cortex-memory:end -->"
    if start in existing and end in existing:
        before, tail = existing.split(start, 1)
        _, after = tail.split(end, 1)
        return before + CLAUDE_MD_CONTENT.rstrip() + after
    if LEGACY_CLAUDE_MD_CONTENT in existing:
        return existing.replace(LEGACY_CLAUDE_MD_CONTENT, CLAUDE_MD_CONTENT, 1)
    return existing.rstrip() + ("\n\n" if existing.strip() else "") + CLAUDE_MD_CONTENT


def run_setup(hooks_only: bool = False) -> None:
    print()
    print("  Cortex Claude Setup")
    print("  ====================")
    print()

    # Tracks (step_name, ok, detail) for every step below, so the summary
    # at the end can tell the user exactly what worked and what didn't
    # instead of silently swallowing failures — this is what made it hard
    # for users to tell why an install "didn't work".
    results: list[tuple[str, bool, str]] = []

    # 1. Create data directory
    try:
        CORTEX_HOME.mkdir(parents=True, exist_ok=True)
        (CORTEX_HOME / "scopes").mkdir(exist_ok=True)
        _ok(f"Data directory: {CORTEX_HOME}")
        results.append(("Data directory", True, ""))
    except Exception as e:
        _fail(f"Data directory: {e}")
        results.append(("Data directory", False, str(e)))

    # 2. Install hooks
    try:
        HOOKS_DIR.mkdir(parents=True, exist_ok=True)

        session_start = HOOKS_DIR / "session-start.sh"
        session_start.write_text(SESSION_START_HOOK)
        session_start.chmod(session_start.stat().st_mode | stat.S_IEXEC)

        user_prompt = HOOKS_DIR / "user-prompt-submit.sh"
        user_prompt.write_text(USER_PROMPT_HOOK)
        user_prompt.chmod(user_prompt.stat().st_mode | stat.S_IEXEC)

        pre_tool_use = HOOKS_DIR / "pre-tool-use.sh"
        pre_tool_use.write_text(PRE_TOOL_USE_HOOK)
        pre_tool_use.chmod(pre_tool_use.stat().st_mode | stat.S_IEXEC)

        post_tool_use = HOOKS_DIR / "post-tool-use.sh"
        post_tool_use.write_text(POST_TOOL_USE_HOOK)
        post_tool_use.chmod(post_tool_use.stat().st_mode | stat.S_IEXEC)

        for name, body in (("stop.sh", STOP_HOOK), ("post-tool-failure.sh", FAILURE_HOOK), ("pre-compact.sh", _hook_launcher('PreCompact')), ("session-end.sh", _hook_launcher('SessionEnd'))):
            script = HOOKS_DIR / name
            script.write_text(body)
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
        _ok(f"Hooks installed: {HOOKS_DIR}")
        results.append(("Hooks installed", True, ""))
    except Exception as e:
        _fail(f"Hooks installed: {e}")
        results.append(("Hooks installed", False, str(e)))
        session_start = HOOKS_DIR / "session-start.sh"
        user_prompt = HOOKS_DIR / "user-prompt-submit.sh"
        pre_tool_use = HOOKS_DIR / "pre-tool-use.sh"
        post_tool_use = HOOKS_DIR / "post-tool-use.sh"

    # 3. Configure Claude Code MCP (global)
    try:
        mcp_config = {}
        if CLAUDE_CONFIG.exists():
            try:
                with open(CLAUDE_CONFIG) as f:
                    mcp_config = json.load(f)
            except json.JSONDecodeError as error:
                raise ValueError("Invalid Claude MCP config; leaving it untouched") from error

        # Use the installed `cortex-claude` binary directly rather than
        # "python3 -m cortex_claude": when installed via `uv tool install`
        # (or any isolated venv), the system's bare `python3` may not have
        # cortex_claude importable at all — it lives in the tool's own
        # venv. shutil.which resolves the absolute path so Claude Code
        # doesn't depend on PATH resolution at MCP launch time.
        cortex_bin = str(Path(sys.executable).parent / "cortex-claude")
        if not Path(cortex_bin).exists():
            cortex_bin = shutil.which("cortex-claude") or "cortex-claude"
        mcp_config.setdefault("mcpServers", {}).setdefault("cortex", {}).update({
            "type": "stdio",
            "command": cortex_bin,
            "args": [],
        })

        write_json_safely(CLAUDE_CONFIG, mcp_config)

        _ok(f"MCP server configured: {CLAUDE_CONFIG}")
        results.append(("MCP server configured", True, ""))
    except Exception as e:
        _fail(f"MCP server configured: {e}")
        results.append(("MCP server configured", False, str(e)))

    # 4. Configure hooks in Claude settings (global)
    try:
        CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)

        settings = {}
        if CLAUDE_SETTINGS.exists():
            try:
                with open(CLAUDE_SETTINGS) as f:
                    settings = json.load(f)
            except json.JSONDecodeError as error:
                raise ValueError("Invalid Claude settings; leaving them untouched") from error

        hooks = settings.setdefault("hooks", {})

        entries = {
            "SessionStart": {"type": "command", "command": str(session_start), "timeout": 5},
            "UserPromptSubmit": {"type": "command", "command": str(user_prompt), "timeout": 3},
            "PostToolUse": {"type": "command", "command": str(post_tool_use), "timeout": 3},
            "PostToolUseFailure": {"type": "command", "command": str(HOOKS_DIR / "post-tool-failure.sh"), "timeout": 3},
            "Stop": {"type": "command", "command": str(HOOKS_DIR / "stop.sh"), "timeout": 5},
            "PreCompact": {"type": "command", "command": str(HOOKS_DIR / "pre-compact.sh"), "timeout": 5},
            "SessionEnd": {"type": "command", "command": str(HOOKS_DIR / "session-end.sh"), "timeout": 3},
        }
        # Keep unrelated hooks. Re-running setup replaces only Cortex entries.
        # PreToolUse is no longer installed: rewriting commands changes what
        # users/tools asked for. Token reduction belongs in retrieval.
        merge_cortex_hooks(hooks, entries)
        write_json_safely(CLAUDE_SETTINGS, settings)

        _ok(f"Hooks configured: {CLAUDE_SETTINGS}")
        results.append(("Hooks configured in settings.json", True, ""))
    except Exception as e:
        _fail(f"Hooks configured: {e}")
        results.append(("Hooks configured in settings.json", False, str(e)))

    # 5. Create/update CLAUDE.md
    try:
        CLAUDE_MD.parent.mkdir(parents=True, exist_ok=True)

        existing = CLAUDE_MD.read_text() if CLAUDE_MD.exists() else ""
        updated = update_memory_instructions(existing)
        if updated != existing:
            backup_file(CLAUDE_MD)
            CLAUDE_MD.write_text(updated)
        _ok(f"Cortex instructions updated: {CLAUDE_MD}")
        results.append(("CLAUDE.md instructions", True, ""))
    except Exception as e:
        _fail(f"CLAUDE.md instructions: {e}")
        results.append(("CLAUDE.md instructions", False, str(e)))

    if hooks_only:
        failed = [name for name, ok, _ in results if not ok]
        if failed:
            raise RuntimeError("Setup failed: " + ", ".join(failed))
        _ok("Shared learning hooks installed. Restart Claude Code to activate.")
        return

    # 6. Download spaCy model
    _print("Downloading spaCy model (en_core_web_sm)...")
    try:
        import spacy
        try:
            spacy.load("en_core_web_sm")
            _skip("spaCy model already installed")
        except OSError:
            _download_spacy_model("en_core_web_sm")
            _ok("spaCy model downloaded")
        results.append(("spaCy model (en_core_web_sm)", True, ""))
    except ImportError:
        _fail("spaCy not installed — fact extraction will be degraded")
        results.append(("spaCy model (en_core_web_sm)", False, "spacy not importable"))
    except Exception as e:
        _fail(f"spaCy model download: {e}")
        results.append(("spaCy model (en_core_web_sm)", False, str(e)))

    # 7. Pre-warm embedding model
    _print("Downloading embedding model (all-MiniLM-L6-v2)...")
    try:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer("all-MiniLM-L6-v2")
        _ok("Embedding model ready")
        results.append(("Embedding model (all-MiniLM-L6-v2)", True, ""))
    except Exception as e:
        _fail(f"Embedding model download: {e}")
        results.append(("Embedding model (all-MiniLM-L6-v2)", False, str(e)))

    # 8. Prepare the shared-learning model. Runtime hooks never download it.
    try:
        from cortex_claude.learning.config import LearningConfig
        from cortex_claude.learning.semantic import SemanticService
        learning_config = LearningConfig.load(CORTEX_HOME)
        if learning_config.semantic_enabled:
            _print("Preparing local multilingual learning model...")
            service = SemanticService(learning_config)
            ready = service.prepare() or service.prepare(download=True)
            results.append(("Multilingual learning model", ready, "" if ready else service.status))
            if ready:
                _ok("Multilingual learning model ready")
            else:
                _fail("Semantic model unavailable; lexical learning still works. Retry: cortex-claude learning prepare")
            del service  # The daemon owns the resident copy.
    except Exception as e:
        results.append(("Multilingual learning model", False, str(e)))

    # 9. Start daemon
    _print("Starting Cortex daemon...")
    try:
        from cortex_claude.daemon import ensure_running, is_running
        ensure_running()
        if is_running():
            _ok("Daemon running")
            results.append(("Background daemon", True, ""))
        else:
            _print("Daemon may take a few seconds to start")
            results.append(("Background daemon", True, "starting"))
    except Exception as e:
        _fail(f"Daemon start: {e}")
        results.append(("Background daemon", False, str(e)))

    # Summary
    print()
    failed = [(name, detail) for name, ok, detail in results if not ok]
    spacy_failed = any(name.startswith("spaCy model") and not ok for name, ok, _ in results)
    embedding_failed = any(name.startswith("Embedding model") and not ok for name, ok, _ in results)
    print(f"  Setup finished: {len(results) - len(failed)}/{len(results)} steps OK")
    if failed:
        print()
        print("  Failed steps:")
        for name, detail in failed:
            print(f"    - {name}: {detail}")
        print()
        print("  cortex-claude setup is safe to re-run after fixing the issue above.")
        if spacy_failed or embedding_failed:
            print()
            print("  Model downloads most commonly fail due to network/proxy/firewall")
            print("  restrictions. You can retry just the failed step(s) manually:")
            if spacy_failed:
                print("    uv run python -m spacy download en_core_web_sm")
            if embedding_failed:
                print("    uv run python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')\"")
        print()
        return

    # Done
    print()
    print("  Setup complete!")
    print()
    print("  Cortex is now configured globally for Claude Code.")
    print("  Restart Claude Code to activate.")
    print()
    print("  Usage:")
    print("    Just talk to Claude — memories are captured automatically.")
    print("    Use 'cortex_recall', 'cortex_facts', 'cortex_traverse' to query.")
    print()
