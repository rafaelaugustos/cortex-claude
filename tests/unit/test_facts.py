from cortex_claude.facts import extract_facts


def test_extract_spacy_svo():
    text = "The auth service uses JWT tokens."
    facts = extract_facts(text)
    subjects = [f.subject for f in facts]
    assert any("auth" in s for s in subjects)


def test_extract_multiple_facts():
    text = "The API uses Redis for caching. The frontend uses React for rendering."
    facts = extract_facts(text)
    assert len(facts) >= 2


def test_extract_empty():
    facts = extract_facts("")
    assert facts == []


def test_extract_short_text():
    facts = extract_facts("Hello world")
    assert isinstance(facts, list)


def test_confidence_ordering():
    text = "The service uses JWT. Rate limit: 1000 req/min."
    facts = extract_facts(text)
    if len(facts) >= 2:
        confidences = [f.confidence for f in facts]
        assert confidences == sorted(confidences, reverse=True)
