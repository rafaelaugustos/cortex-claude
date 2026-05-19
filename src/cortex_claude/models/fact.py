from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return str(uuid.uuid4())


class Fact(BaseModel):
    id: str = Field(default_factory=_new_id)
    subject: str
    relation: str
    object: str
    confidence: float = 1.0
    source_memory_id: str | None = ""
    scope: str = "global"
    created_at: int = Field(default_factory=_now_ms)
    temporal: str | None = None
    access_count: int = 0


class FactQuery(BaseModel):
    topic: str
    relation: str | None = None
    scope: str | None = None
    limit: int = 20
