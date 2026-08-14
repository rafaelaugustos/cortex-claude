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
