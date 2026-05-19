from __future__ import annotations

import pytest

from cortex_claude.capture import (
    CaptureContext,
    CaptureDecision,
    CaptureFilter,
    CaptureFilterConfig,
)


@pytest.fixture
def filter_default() -> CaptureFilter:
    return CaptureFilter()


def _ctx(content: str, tags: list[str]) -> CaptureContext:
    return CaptureContext(content=content, tags=tags)


class TestCaptureFilter:
    def test_drops_ls_command(self, filter_default: CaptureFilter):
        d, _ = filter_default.decide(
            _ctx("Command: ls -la\nResult: total 24", ["auto-capture", "bash"])
        )
        assert d == CaptureDecision.DROP

    def test_drops_short_read(self, filter_default: CaptureFilter):
        d, _ = filter_default.decide(
            _ctx("Read file: /tmp/x\nPreview: hi", ["auto-capture", "file-read"])
        )
        assert d == CaptureDecision.DROP

    def test_keeps_file_read_with_signal_keyword(self, filter_default: CaptureFilter):
        content = "Read file: /tmp/x\nPreview: " + "fix the bug because root cause was X" * 3
        d, _ = filter_default.decide(_ctx(content, ["auto-capture", "file-read"]))
        assert d == CaptureDecision.KEEP

    def test_keeps_agent_always(self, filter_default: CaptureFilter):
        d, reason = filter_default.decide(
            _ctx("Agent task: x\nResult: y", ["auto-capture", "agent"])
        )
        assert d == CaptureDecision.KEEP
        assert reason.startswith("keep-tool")

    def test_passes_explicit_save_through(self, filter_default: CaptureFilter):
        d, reason = filter_default.decide(_ctx("anything", ["important"]))
        assert d == CaptureDecision.KEEP
        assert reason == "explicit-save"

    def test_drops_edit_with_no_signal(self, filter_default: CaptureFilter):
        d, _ = filter_default.decide(
            _ctx('Edited /x: replaced "foo" with "bar"', ["auto-capture", "file-change"])
        )
        assert d == CaptureDecision.DROP

    def test_keeps_edit_with_signal(self, filter_default: CaptureFilter):
        d, _ = filter_default.decide(
            _ctx(
                'Edited /x: replaced "foo" with "bar to fix the bug because regression"',
                ["auto-capture", "file-change"],
            )
        )
        assert d == CaptureDecision.KEEP

    def test_summary_for_ambiguous(self, filter_default: CaptureFilter):
        content = "Command: docker ps\nResult: " + "CONTAINER ID  IMAGE  STATUS " * 8
        d, _ = filter_default.decide(_ctx(content, ["auto-capture", "bash"]))
        assert d == CaptureDecision.KEEP_SUMMARY

    def test_disabled_passes_everything(self):
        f = CaptureFilter(CaptureFilterConfig(enabled=False))
        d, _ = f.decide(_ctx("ls", ["auto-capture", "bash"]))
        assert d == CaptureDecision.KEEP


class TestCaptureFilterConfig:
    def test_from_empty_dict(self):
        cfg = CaptureFilterConfig.from_dict({})
        assert cfg.enabled is True
        assert cfg.llm_judge_enabled is False

    def test_from_full_dict(self):
        cfg = CaptureFilterConfig.from_dict({
            "enabled": False,
            "min_content_length": 5,
            "llm_judge": {"enabled": True, "endpoint": "http://x", "timeout_ms": 500},
        })
        assert cfg.enabled is False
        assert cfg.min_content_length == 5
        assert cfg.llm_judge_enabled is True
        assert cfg.llm_judge_endpoint == "http://x"
        assert cfg.llm_judge_timeout_ms == 500
