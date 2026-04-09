from cortex_claude.core.token_budget import TokenBudget


def test_initial_state():
    budget = TokenBudget(max_tokens=100)
    assert budget.remaining == 100
    assert budget.used_tokens == 0


def test_consume_within_budget():
    budget = TokenBudget(max_tokens=100)
    assert budget.consume(50) is True
    assert budget.remaining == 50


def test_consume_exceeds_budget():
    budget = TokenBudget(max_tokens=100)
    budget.consume(80)
    assert budget.consume(30) is False
    assert budget.used_tokens == 80


def test_consume_exact_budget():
    budget = TokenBudget(max_tokens=100)
    assert budget.consume(100) is True
    assert budget.remaining == 0
    assert budget.consume(1) is False
