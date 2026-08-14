from __future__ import annotations

from pathlib import Path

import pytest

from cortex_claude.core.engine import CortexEngine
from cortex_claude.daemon import CortexDaemon
from cortex_claude.server.config import CortexConfig


def _make_daemon(engine: CortexEngine) -> CortexDaemon:
    """Build a CortexDaemon without running its real __init__ (which loads
    config from the user's actual ~/.cortex-claude via CortexConfig.load()).
    Only the state _maybe_index_project/_run_project_scan actually touch is
    set up here."""
    daemon = object.__new__(CortexDaemon)
    daemon._engine = engine
    daemon._project_scan_in_flight = set()
    daemon._project_scan_tasks = {}
    return daemon


@pytest.fixture
def engine(tmp_path: Path) -> CortexEngine:
    config = CortexConfig(base_path=tmp_path / ".cortex-claude")
    eng = CortexEngine(config=config)
    eng.initialize()
    yield eng
    eng.close()


def _write_py_files(project_dir: Path, count: int) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (project_dir / f"mod_{i}.py").write_text(f"def func_{i}():\n    pass\n")


@pytest.mark.asyncio
async def test_first_scan_indexes_project_into_derived_scope(engine: CortexEngine, tmp_path: Path):
    project_dir = tmp_path / "my-project"
    _write_py_files(project_dir, 3)

    daemon = _make_daemon(engine)
    result = daemon._maybe_index_project(str(project_dir))
    assert result["started"] is True
    scope = result["scope"]
    assert scope == "project:my-project"

    # The scan runs as a background asyncio task; await it directly instead
    # of scanning asyncio.all_tasks() (which could pick up unrelated tasks).
    await daemon._project_scan_tasks[scope]

    conn = engine.get_scope_connection(scope)
    rows = conn.execute(
        "SELECT COUNT(*) FROM facts WHERE scope = ? AND relation = 'defined_in'",
        (scope,),
    ).fetchone()
    assert rows[0] == 3


@pytest.mark.asyncio
async def test_second_scan_is_skipped_when_already_indexed(engine: CortexEngine, tmp_path: Path):
    project_dir = tmp_path / "already-done"
    _write_py_files(project_dir, 2)

    daemon = _make_daemon(engine)
    first = daemon._maybe_index_project(str(project_dir))
    assert first["started"] is True
    await daemon._project_scan_tasks[first["scope"]]

    second = daemon._maybe_index_project(str(project_dir))
    assert second["skipped"] == "already-indexed"
    assert second["scope"] == first["scope"]


@pytest.mark.asyncio
async def test_concurrent_scan_of_same_scope_is_not_duplicated(engine: CortexEngine, tmp_path: Path):
    project_dir = tmp_path / "concurrent-project"
    _write_py_files(project_dir, 2)

    daemon = _make_daemon(engine)
    first = daemon._maybe_index_project(str(project_dir))
    assert first["started"] is True

    # Second call before the first scan's background task has completed.
    second = daemon._maybe_index_project(str(project_dir))
    assert second["skipped"] == "already-in-flight"
    assert second["scope"] == first["scope"]

    await daemon._project_scan_tasks[first["scope"]]


@pytest.mark.asyncio
async def test_max_files_limit_is_respected(engine: CortexEngine, tmp_path: Path):
    from cortex_claude.server.tools.code import handle_index_code

    project_dir = tmp_path / "big-project"
    _write_py_files(project_dir, 5)

    result = await handle_index_code(
        engine, cwd=str(project_dir), path=str(project_dir),
        scope="project:big-project", max_files=2,
    )
    assert "Indexed 2 files" in result
    assert "max_files=2" in result
