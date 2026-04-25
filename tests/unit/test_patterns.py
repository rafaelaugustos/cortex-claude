from cortex_claude.facts.patterns import extract_facts_patterns


def test_bullet_list():
    text = "- spaCy for NLP\n- Redis for caching\n- SQLite for storage"
    facts = extract_facts_patterns(text)
    subjects = [f.subject for f in facts]
    assert "spacy" in subjects
    assert "redis" in subjects


def test_bullet_list_pt():
    text = "- spaCy para NLP\n- Redis para cache"
    facts = extract_facts_patterns(text)
    assert len(facts) >= 2


def test_key_value():
    text = "Database: PostgreSQL\nCache: Redis"
    facts = extract_facts_patterns(text)
    assert any(f.object == "postgresql" for f in facts)
    assert any(f.object == "redis" for f in facts)


def test_key_comma_list():
    text = "Stack: Python, spaCy, SQLite, Redis"
    facts = extract_facts_patterns(text)
    objects = [f.object for f in facts]
    assert "python" in objects
    assert "redis" in objects


def test_with_for():
    text = "PostgreSQL with pgvector for vector search"
    facts = extract_facts_patterns(text)
    has_uses = any(f.relation == "uses" for f in facts)
    assert has_uses


def test_parenthetical():
    text = "FastAPI (Python) handles the API"
    facts = extract_facts_patterns(text)
    assert any(f.subject == "fastapi" and f.object == "python" for f in facts)


def test_slash_separated():
    text = "Frontend: React/TypeScript"
    facts = extract_facts_patterns(text)
    objects = [f.object for f in facts]
    assert "react" in objects
    assert "typescript" in objects


def test_uses_comma_list():
    text = "The project uses Python, Redis, and PostgreSQL"
    facts = extract_facts_patterns(text)
    objects = [f.object for f in facts]
    assert "python" in objects
    assert "redis" in objects
    assert "postgresql" in objects


def test_exposes_list():
    text = "The server exposes save, recall, and facts tools"
    facts = extract_facts_patterns(text)
    assert len(facts) >= 3
