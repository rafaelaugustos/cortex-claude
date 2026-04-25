import os

from cortex_claude.facts.extractor import _should_use_claude, extract_facts
from cortex_claude.models.fact import Fact


def test_should_use_claude_with_no_facts():
    assert _should_use_claude([], 0.5) is True


def test_should_use_claude_with_few_facts():
    facts = [Fact(subject="a", relation="b", object="c", confidence=0.3)]
    assert _should_use_claude(facts, 0.5) is True


def test_should_not_use_claude_with_enough_facts():
    facts = [
        Fact(subject="a", relation="b", object="c", confidence=0.8),
        Fact(subject="d", relation="e", object="f", confidence=0.7),
    ]
    assert _should_use_claude(facts, 0.5) is False


def test_claude_fallback_disabled_by_default():
    facts = extract_facts("Some text here", claude_fallback=False)
    assert isinstance(facts, list)


def test_claude_fallback_no_api_key():
    old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        facts = extract_facts(
            "Simple text with no clear facts",
            claude_fallback=True,
        )
        assert isinstance(facts, list)
    finally:
        if old_key:
            os.environ["ANTHROPIC_API_KEY"] = old_key
