from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenBudget:
    max_tokens: int
    used_tokens: int = field(default=0)

    @property
    def remaining(self) -> int:
        return self.max_tokens - self.used_tokens

    def consume(self, tokens: int) -> bool:
        if self.used_tokens + tokens > self.max_tokens:
            return False
        self.used_tokens += tokens
        return True
