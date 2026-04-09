from __future__ import annotations

from pathlib import Path

import pytest

from cortex_claude.core.engine import CortexEngine
from cortex_claude.storage.database import StorageManager


@pytest.fixture
def tmp_cortex_home(tmp_path: Path) -> Path:
    home = tmp_path / ".cortex-claude"
    home.mkdir()
    return home


@pytest.fixture
def storage_manager(tmp_cortex_home: Path) -> StorageManager:
    manager = StorageManager(base_path=tmp_cortex_home)
    yield manager
    manager.close_all()


@pytest.fixture
def engine(tmp_cortex_home: Path) -> CortexEngine:
    eng = CortexEngine(base_path=tmp_cortex_home)
    yield eng
    eng.close()
