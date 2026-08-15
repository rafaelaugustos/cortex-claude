from __future__ import annotations

import pytest

from cortex_claude.core.engine import CortexEngine
from cortex_claude.server.tools.code import handle_code, handle_index_code


@pytest.mark.asyncio
async def test_reindex_removes_stale_symbols(engine: CortexEngine, tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "def foo():\n    pass\n\ndef removed_later():\n    pass\n"
    )
    await handle_index_code(engine, cwd=str(tmp_path), path=str(f), scope="global")

    result = await handle_code(engine, cwd=str(tmp_path), symbol="removed_later", scope="global")
    assert "defined_in" in result

    # Edit the file to remove `removed_later` and reindex.
    f.write_text("def foo():\n    pass\n")
    await handle_index_code(engine, cwd=str(tmp_path), path=str(f), scope="global")

    result = await handle_code(engine, cwd=str(tmp_path), symbol="removed_later", scope="global")
    assert "not found" in result

    result = await handle_code(engine, cwd=str(tmp_path), symbol="foo", scope="global")
    assert "defined_in" in result


@pytest.mark.asyncio
async def test_reindex_is_idempotent_no_duplicate_facts(engine: CortexEngine, tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("def foo():\n    pass\n")

    await handle_index_code(engine, cwd=str(tmp_path), path=str(f), scope="global")
    await handle_index_code(engine, cwd=str(tmp_path), path=str(f), scope="global")

    conn = engine.get_scope_connection("global")
    rows = conn.execute(
        "SELECT COUNT(*) FROM facts WHERE subject = 'foo' AND relation = 'defined_in'"
    ).fetchone()
    assert rows[0] == 1


@pytest.mark.asyncio
async def test_handle_code_groups_same_name_symbols_by_file(engine: CortexEngine, tmp_path):
    """Two files defining a function with the same name are shown as
    separate defined_in sections instead of one ambiguous merged block.
    Note: this groups `defined_in`/`calls_from` by file — plain `calls`
    (which has no per-file qualifier in the schema) is still shown for
    both files under each section; see code/facts.py docstring for why
    that's a documented, partial mitigation rather than full resolution."""
    file_a = tmp_path / "a.py"
    file_a.write_text("from helpers import helper_from_a\n\ndef run():\n    helper_from_a()\n")
    file_b = tmp_path / "b.py"
    file_b.write_text("def run():\n    helper_from_b()\n")

    await handle_index_code(engine, cwd=str(tmp_path), path=str(file_a), scope="global")
    await handle_index_code(engine, cwd=str(tmp_path), path=str(file_b), scope="global")

    result = await handle_code(engine, cwd=str(tmp_path), symbol="run", scope="global")
    # Both files' definitions are present, in distinct sections.
    assert str(file_a) in result
    assert str(file_b) in result

    # Explicit "path:name" form narrows to just that file's section, and
    # its resolved (calls_from) call is qualified to that file only.
    scoped_result = await handle_code(
        engine, cwd=str(tmp_path), symbol=f"{file_a}:run", scope="global"
    )
    assert str(file_a) in scoped_result
    assert str(file_b) not in scoped_result
    assert "helpers:helper_from_a" in scoped_result

    scoped_result_b = await handle_code(
        engine, cwd=str(tmp_path), symbol=f"{file_b}:run", scope="global"
    )
    assert "helpers:helper_from_a" not in scoped_result_b
