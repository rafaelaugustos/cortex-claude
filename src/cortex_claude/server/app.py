from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from cortex_claude.core.engine import CortexEngine
from cortex_claude.server.config import CortexConfig
from cortex_claude.server.tools.clusters import handle_clusters
from cortex_claude.server.tools.code import handle_code, handle_index_code
from cortex_claude.server.tools.facts import handle_facts
from cortex_claude.server.tools.forget import handle_forget
from cortex_claude.server.tools.recall import handle_recall
from cortex_claude.server.tools.save import handle_save
from cortex_claude.server.tools.scopes import handle_scopes
from cortex_claude.server.tools.status import handle_status
from cortex_claude.server.tools.traverse import handle_traverse
from cortex_claude.server.tools.learn import handle_learn

mcp = FastMCP("cortex-claude")
engine: CortexEngine | None = None


def _get_engine() -> CortexEngine:
    if engine is None:
        _init_engine()
    assert engine is not None
    return engine


def _init_engine() -> None:
    global engine
    base_path = Path(
        os.environ.get("CORTEX_HOME", str(Path.home() / ".cortex-claude"))
    ).expanduser()
    config = CortexConfig.load(base_path)
    engine = CortexEngine(config=config)
    engine.initialize()
    from cortex_claude.reliability.files import state
    import time
    client = os.environ.get('CORTEX_CLIENT', 'claude')
    if client in {'claude', 'codex'}:
        state(base_path, **{f'mcp_{client}_at': time.time()})


def _cwd() -> str:
    return os.getcwd()


@mcp.tool()
async def cortex_learn(
    content: str = "",
    topic: str = "",
    applicability: Literal["personal", "transferable", "context"] = "context",
    triggers: str = "",
    explicit: bool = False,
    action: Literal["observe", "correct", "experience", "outcome", "read", "feedback", "forget", "list", "status"] = "observe",
    lesson_id: str | None = None,
    conditions: dict[str, list[str]] | None = None,
    experience: dict[str, str] | None = None,
    dependencies: list[str] | None = None,
    max_age_days: int | None = None,
    verification_id: str | None = None,
    outcome: Literal["passed", "failed"] = "passed",
    session_id: str | None = None,
    max_tokens: int | None = None,
    query: str = "",
    assessment: Literal["", "useful", "irrelevant", "corrected"] = "",
) -> str:
    """Learn a <=80-token conclusion with a stable topic. personal: 3 sessions; transferable: also 2 origins; context: local. explicit only for standing user instructions. conditions: all/any/none task cues; dependencies: relative files to watch. experience: {situation,cause,solution}; validation requires a successful test verification_id (status lists receipts; 'latest' only if that test verifies this solution). outcome records passed/failed application. read returns details by lesson_id; supply query for conditions. feedback assessment=useful/irrelevant/corrected improves selection without adding evidence; use only after evaluating a delivered lesson, never merely reading it."""
    home = Path(os.environ.get("CORTEX_HOME", "~/.cortex-claude")).expanduser()
    return handle_learn(home, _cwd(), action, content, topic, applicability,
                        triggers, explicit, lesson_id, conditions=conditions, experience=experience,
                        dependencies=dependencies, max_age_days=max_age_days, verification_id=verification_id,
                        outcome=outcome, session_id=session_id, max_tokens=max_tokens, query=query, assessment=assessment)


@mcp.tool()
async def cortex_read(path: str, start_line: int = 1, end_line: int | None = None,
                      max_tokens: int = 800, mode: Literal["auto", "full"] = "auto",
                      session_id: str | None = None) -> str:
    """Read source lines within a token budget. auto returns a verified diff or unchanged marker after this session has seen the base; full forces content. Files must be inside the repository. No command rewriting. Supply session_id when concurrent sessions make delivery identity ambiguous."""
    from cortex_claude.learning.store import LearningStore
    from cortex_claude.learning.reading import read_file
    home = Path(os.environ.get("CORTEX_HOME", "~/.cortex-claude")).expanduser()
    try:
        with LearningStore(home) as store:
            return read_file(store, _cwd(), path, session_id, start_line, end_line, max_tokens, mode)
    except (ValueError, OSError) as error:
        return json.dumps({"error": str(error)})


@mcp.tool()
async def cortex_task(action: Literal["save", "list", "resume", "complete", "forget"],
                      task_id: str | None = None, title: str = "", summary: str = "", next_step: str = "",
                      decisions: list[str] | None = None, pending: list[str] | None = None,
                      dependencies: list[str] | None = None, expected_revision: int | None = None,
                      session_id: str | None = None) -> str:
    """Save/resume a compact work checkpoint (<=240 tokens; 14-day validity) at meaningful milestones. Preserve decisions, pending work and next step. Updates/complete/forget require expected_revision to prevent overwrites. Origin-bound in the shared database. Recheck files when needs_review=true. Never turn task state into a personal preference."""
    from cortex_claude.learning.store import LearningStore
    from cortex_claude.learning.tasks import handle_task
    home = Path(os.environ.get("CORTEX_HOME", "~/.cortex-claude")).expanduser()
    try:
        with LearningStore(home) as store:
            result = handle_task(store, _cwd(), action, task_id, expected_revision, session_id or store.delivery_session(_cwd()),
                                 title=title, summary=summary, next_step=next_step, decisions=decisions, pending=pending, dependencies=dependencies)
            return json.dumps(result, ensure_ascii=False)
    except (ValueError, OSError) as error:
        return json.dumps({"error": str(error)})


@mcp.tool()
async def cortex_project(action: Literal["read", "refresh", "note", "forget_note"] = "read",
                         section: Literal["purpose", "architecture", "conventions", "decisions"] = "architecture",
                         content: str = "", sources: list[str] | None = None,
                         note_id: str | None = None, max_tokens: int = 800) -> str:
    """Project knowledge in the shared database, tied to this repository. refresh reads bounded manifests/docs without executing commands. read returns declared stack, commands, modules, and sourced conclusions. note records your synthesis after reading supporting files (1-5 sources, <=160 tokens), not transcripts or guesses. File changes flag notes for review. forget_note removes a conclusion. Read native files when a complete architectural analysis is still pending."""
    from cortex_claude.learning.projects import add_note, read_project, refresh_project
    from cortex_claude.learning.store import LearningStore, context_origin
    home = Path(os.environ.get("CORTEX_HOME", "~/.cortex-claude")).expanduser()
    try:
        with LearningStore(home) as store:
            if not store.config.enabled or not store.config.project_memory:
                return json.dumps({"status": "disabled"})
            if action == "refresh":
                refresh_project(store, _cwd())
            elif action == "note":
                return json.dumps(add_note(store, _cwd(), section, content, sources or []), ensure_ascii=False)
            elif action == "forget_note":
                with store.conn:
                    deleted = store.conn.execute("DELETE FROM project_notes WHERE id=? AND origin=?", (note_id, context_origin(_cwd()))).rowcount
                    if deleted:
                        store.conn.execute("UPDATE project_profiles SET revision=revision+1 WHERE origin=?", (context_origin(_cwd()),))
                return json.dumps({"deleted": bool(deleted)})
            return json.dumps(read_project(store, _cwd(), max_tokens), ensure_ascii=False)
    except (ValueError, OSError) as error:
        return json.dumps({"error": str(error)})


@mcp.tool()
async def cortex_save(
    content: str,
    tags: list[str] | None = None,
    scope: str | None = None,
) -> str:
    """Archive reference information with facts, a summary and embeddings. Use cortex_learn for preferences and reusable lessons."""
    return await handle_save(_get_engine(), content, _cwd(), tags, scope)


@mcp.tool()
async def cortex_recall(
    query: str,
    max_tokens: int = 200,
    scope: str | None = None,
    depth: Literal["auto", "facts", "summaries", "full"] = "auto",
) -> str:
    """Retrieve learned and archived context within max_tokens. depth: auto, facts, summaries or full. Skip when the needed context was already supplied automatically."""
    return await handle_recall(_get_engine(), query, _cwd(), max_tokens, scope, depth)


@mcp.tool()
async def cortex_facts(
    topic: str,
    relation: str | None = None,
    scope: str | None = None,
    limit: int = 20,
) -> str:
    """Query subject-relation-object facts by topic, optionally filtering relation and scope."""
    return await handle_facts(_get_engine(), topic, _cwd(), relation, scope, limit)


@mcp.tool()
async def cortex_traverse(
    start: str,
    max_hops: int = 2,
    scope: str | None = None,
) -> str:
    """Follow knowledge-graph connections up to max_hops. start accepts an entity or cluster:<id>."""
    return await handle_traverse(_get_engine(), start, _cwd(), max_hops, scope)


@mcp.tool()
async def cortex_forget(
    query: str | None = None,
    memory_id: str | None = None,
    scope: str | None = None,
    dry_run: bool = True,
) -> str:
    """Delete archived memories by query or ID. dry_run=true previews. Use cortex_learn action=forget for learned preferences."""
    return await handle_forget(_get_engine(), _cwd(), query, memory_id, scope, dry_run)


@mcp.tool()
async def cortex_scopes(
    action: Literal["list", "create", "delete", "link", "unlink", "info"],
    name: str | None = None,
    path: str | None = None,
) -> str:
    """Manage legacy archive scopes and directory mappings: list, create, delete, link, unlink or info. Shared learning requires no scope setup."""
    return await handle_scopes(_get_engine(), action, _cwd(), name, path)


@mcp.tool()
async def cortex_status(
    scope: str | None = None,
) -> str:
    """Show archive statistics, shared learning counts and estimated context tokens injected/avoided."""
    return await handle_status(_get_engine(), _cwd(), scope)


@mcp.tool()
async def cortex_code(
    symbol: str,
    scope: str | None = None,
) -> str:
    """Look up a symbol definition, callers, callees and imports before reading a whole file. Accepts path:symbol to disambiguate."""
    return await handle_code(_get_engine(), _cwd(), symbol, scope)


@mcp.tool()
async def cortex_index_code(
    path: str,
    scope: str | None = None,
    recursive: bool = True,
) -> str:
    """Index source symbols and calls from a file/directory. Supports Python, JS/TS, Go, Java, Swift and Kotlin; skips dependency/build directories."""
    return await handle_index_code(_get_engine(), _cwd(), path, scope, recursive)


@mcp.tool()
async def cortex_clusters(
    action: Literal["list", "backfill"] = "list",
    scope: str | None = None,
    limit: int = 50,
) -> str:
    """List semantic archive clusters or rebuild them with action=backfill."""
    return await handle_clusters(_get_engine(), _cwd(), action, scope, limit)
