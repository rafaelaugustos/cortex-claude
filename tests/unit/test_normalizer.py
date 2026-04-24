from cortex_claude.facts.normalizer import (
    CANONICAL_ALIASES,
    entities_match,
    find_canonical,
    normalize_entity,
)


def test_normalize_strips_articles():
    assert normalize_entity("the auth service") == "auth service"
    assert normalize_entity("an API gateway") == "api gateway"


def test_normalize_lowercase():
    assert normalize_entity("PostgreSQL") == "postgresql"


def test_normalize_aliases():
    assert normalize_entity("postgres") == "postgresql"
    assert normalize_entity("js") == "javascript"
    assert normalize_entity("k8s") == "kubernetes"


def test_normalize_whitespace():
    assert normalize_entity("  auth   service  ") == "auth service"


def test_entities_match_identical():
    assert entities_match("postgresql", "postgresql") is True


def test_entities_match_substring():
    assert entities_match("auth", "auth service") is True


def test_entities_match_fuzzy():
    assert entities_match("authentication", "auth service") is False
    assert entities_match("auth-service", "auth service") is True


def test_entities_match_different():
    assert entities_match("postgresql", "redis") is False


def test_find_canonical():
    existing = ["postgresql", "auth service", "redis"]
    assert find_canonical("postgres", existing) == "postgresql"
    assert find_canonical("unknown thing", existing) is None
