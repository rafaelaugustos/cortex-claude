from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class ScopeInfo(BaseModel):
    name: str
    path: Path
    memory_count: int = 0
    size_bytes: int = 0


class ScopeConfig(BaseModel):
    mappings: dict[str, str] = {}
    default: str = "global"
    search_order: str = "project_first"
