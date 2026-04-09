from __future__ import annotations

import time
import uuid
from pydantic import BaseModel, Field


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return str(uuid.uuid4())


class Memory(BaseModel):
    id: str = Field(default_factory=_new_id)
    content: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    scope: str = "global"
    created_at: int = Field(default_factory=_now_ms)
    updated_at: int = Field(default_factory=_now_ms)
    accessed_at: int = Field(default_factory=_now_ms)
    access_count: int = 0
    decay_score: float = 1.0


class SaveResult(BaseModel):
    memory_id: str
    scope: str
    tokens_stored: int


class RecallItem(BaseModel):
    memory_id: str
    content: str
    score: float
    scope: str
    tags: list[str] = Field(default_factory=list)
    created_at: int


class RecallResult(BaseModel):
    memories: list[RecallItem] = Field(default_factory=list)
    total_tokens: int = 0
    query: str
