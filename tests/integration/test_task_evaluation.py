import importlib
from pathlib import Path

import pytest


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "scripts"))
    return importlib.import_module("evaluate_tasks")


def test_realistic_graders_reject_bugs_and_accept_complete_solutions(harness, tmp_path):
    assert len(harness.CASES) == 5
    for case in harness.CASES:
        folder = tmp_path / case["name"]
        harness.write_fixture(folder, case)
        assert harness.grade(folder).returncode != 0, case["name"]
        harness.write_fixture(folder, case, fixed=True)
        assert harness.grade(folder).returncode == 0, case["name"]


def test_regression_gate_rejects_quality_or_token_regressions(harness):
    good = {"task": "example", "quality_preserved": True, "memory": {"quality": 1}, "token_change_percent": -10}
    assert harness.regression([good])["passed"]
    assert not harness.regression([{**good, "token_change_percent": 30}])["passed"]
    assert not harness.regression([{**good, "quality_preserved": False}])["passed"]
    assert not harness.regression([{**good, "memory": {"quality": .5}}])["passed"]
    assert harness.regression([])["passed"] is None


def test_codex_counters_do_not_double_count_cached_input(harness):
    from codex_evaluation import parse_result
    import json
    events = [
        {'type': 'item.completed', 'item': {'id': 'one', 'type': 'command_execution', 'exit_code': 0}},
        {'type': 'turn.completed', 'usage': {'input_tokens': 1000, 'cached_input_tokens': 800, 'output_tokens': 40}},
        {'type': 'turn.completed', 'usage': {'input_tokens': 1200, 'cached_input_tokens': 1000, 'output_tokens': 60}},
    ]
    result, calls, failures = parse_result('\n'.join(map(json.dumps, events)))
    assert result['usage'] == {'input_tokens': 400, 'cache_read_input_tokens': 1800, 'output_tokens': 100, 'cache_creation_input_tokens': 0}
    assert sum(result['usage'].values()) == 2300
    assert calls == 1 and failures == 0
    assert result['total_cost_usd'] is None
    with pytest.raises(RuntimeError):
        parse_result('{"type":"turn.failed"}')
    with pytest.raises(ValueError):
        parse_result(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1, 'cached_input_tokens': 2}}))
