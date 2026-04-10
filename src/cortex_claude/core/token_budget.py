from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenBudget:
    max_tokens: int
    used_tokens: int = field(default=0)

    facts_ratio: float = 0.40
    summaries_ratio: float = 0.35
    chunks_ratio: float = 0.25

    @property
    def remaining(self) -> int:
        return self.max_tokens - self.used_tokens

    @property
    def facts_budget(self) -> int:
        return int(self.max_tokens * self.facts_ratio)

    @property
    def summaries_budget(self) -> int:
        return int(self.max_tokens * self.summaries_ratio)

    @property
    def chunks_budget(self) -> int:
        return int(self.max_tokens * self.chunks_ratio)

    def consume(self, tokens: int) -> bool:
        if self.used_tokens + tokens > self.max_tokens:
            return False
        self.used_tokens += tokens
        return True
