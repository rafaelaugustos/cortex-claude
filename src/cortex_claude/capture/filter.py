from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class CaptureDecision(str, Enum):
    KEEP = "keep"
    DROP = "drop"
    KEEP_SUMMARY = "keep_summary"


@dataclass
class CaptureFilterConfig:
    enabled: bool = True
    min_content_length: int = 60
    min_signal_keywords: int = 1
    keep_tools: tuple[str, ...] = ("agent", "mcp", "web")
    drop_tools: tuple[str, ...] = ()
    keyword_signals: tuple[str, ...] = (
        "fix", "fixed", "bug", "error", "exception", "traceback",
        "because", "root cause", "reason", "decided", "decision",
        "won't work", "doesn't work", "broken", "regression",
        "todo", "fixme", "hack", "workaround",
        "architecture", "refactor", "migration",
        "deprecated", "removed", "breaking change",
    )
    drop_keyword_patterns: tuple[str, ...] = (
        r"^read file:",
        r"^file search:",
        r"^search\s",
        r"^command:\s*(ls|cd|pwd|echo|cat|head|tail|which|chmod|mkdir|touch)",
    )
    llm_judge_enabled: bool = False
    llm_judge_endpoint: str = ""
    llm_judge_timeout_ms: int = 2000

    @classmethod
    def from_dict(cls, raw: dict) -> CaptureFilterConfig:
        cfg = cls()
        if not raw:
            return cfg
        cfg.enabled = raw.get("enabled", cfg.enabled)
        cfg.min_content_length = raw.get("min_content_length", cfg.min_content_length)
        cfg.min_signal_keywords = raw.get("min_signal_keywords", cfg.min_signal_keywords)
        if "keep_tools" in raw:
            cfg.keep_tools = tuple(raw["keep_tools"])
        if "drop_tools" in raw:
            cfg.drop_tools = tuple(raw["drop_tools"])
        if "keyword_signals" in raw:
            cfg.keyword_signals = tuple(raw["keyword_signals"])
        if "drop_keyword_patterns" in raw:
            cfg.drop_keyword_patterns = tuple(raw["drop_keyword_patterns"])
        judge = raw.get("llm_judge", {}) or {}
        cfg.llm_judge_enabled = judge.get("enabled", cfg.llm_judge_enabled)
        cfg.llm_judge_endpoint = judge.get("endpoint", cfg.llm_judge_endpoint)
        cfg.llm_judge_timeout_ms = judge.get("timeout_ms", cfg.llm_judge_timeout_ms)
        return cfg


@dataclass
class CaptureContext:
    content: str
    tags: list[str] = field(default_factory=list)

    @property
    def is_auto_capture(self) -> bool:
        return "auto-capture" in self.tags

    @property
    def tool_tag(self) -> str | None:
        skip = {"auto-capture"}
        for t in self.tags:
            if t not in skip:
                return t
        return None


class CaptureFilter:
    """Decides whether an auto-captured save is worth persisting.

    Two-stage:
      1. Heuristic gate (always runs, local, zero-cost).
      2. Optional LLM-judge for ambiguous cases (off by default).

    Non-auto-capture saves (explicit `cortex_save` calls) always pass through.
    """

    def __init__(self, config: CaptureFilterConfig | None = None) -> None:
        self.config = config or CaptureFilterConfig()
        self._drop_patterns = tuple(
            re.compile(p, re.IGNORECASE) for p in self.config.drop_keyword_patterns
        )
        self._signal_pattern = re.compile(
            r"\b(" + "|".join(re.escape(k) for k in self.config.keyword_signals) + r")\b",
            re.IGNORECASE,
        ) if self.config.keyword_signals else None

    def decide(self, ctx: CaptureContext) -> tuple[CaptureDecision, str]:
        """Returns (decision, reason). Reason is for logging/debugging."""
        if not self.config.enabled:
            return CaptureDecision.KEEP, "filter-disabled"

        if not ctx.is_auto_capture:
            return CaptureDecision.KEEP, "explicit-save"

        content = (ctx.content or "").strip()
        tool = ctx.tool_tag

        if tool and tool in self.config.drop_tools:
            return CaptureDecision.DROP, f"drop-tool:{tool}"

        if tool and tool in self.config.keep_tools:
            return CaptureDecision.KEEP, f"keep-tool:{tool}"

        for pat in self._drop_patterns:
            if pat.search(content):
                if self._signal_count(content) >= self.config.min_signal_keywords:
                    return CaptureDecision.KEEP, "drop-pattern-but-signal"
                return CaptureDecision.DROP, f"drop-pattern:{pat.pattern}"

        if len(content) < self.config.min_content_length:
            if self._signal_count(content) >= self.config.min_signal_keywords:
                return CaptureDecision.KEEP, "short-but-signal"
            return CaptureDecision.DROP, f"too-short:{len(content)}"

        signals = self._signal_count(content)
        if signals >= self.config.min_signal_keywords:
            return CaptureDecision.KEEP, f"signals:{signals}"

        return CaptureDecision.KEEP_SUMMARY, "ambiguous"

    def _signal_count(self, content: str) -> int:
        if not self._signal_pattern:
            return 0
        return len(self._signal_pattern.findall(content))
