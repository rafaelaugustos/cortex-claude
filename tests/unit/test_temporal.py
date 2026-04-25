from cortex_claude.facts.temporal import extract_temporal, attach_temporal_to_facts
from cortex_claude.models.fact import Fact


def test_extract_date_format():
    assert extract_temporal("Deployed on 2024-04-15") == "2024-04-15"


def test_extract_month_year():
    result = extract_temporal("In April 2024, we migrated the database")
    assert result is not None
    assert "april 2024" in result.lower() or "April 2024" in result


def test_extract_month_year_pt():
    result = extract_temporal("Em março de 2025 mudamos a API")
    assert result is not None
    assert "março" in result.lower() or "2025" in result


def test_extract_relative():
    assert extract_temporal("This was changed yesterday") == "yesterday"


def test_extract_ago():
    result = extract_temporal("Updated 3 weeks ago")
    assert result is not None
    assert "weeks ago" in result.lower()


def test_extract_quarter():
    assert extract_temporal("Target is Q3 2025") == "Q3 2025"


def test_extract_change_keyword():
    result = extract_temporal("We switched from MySQL to PostgreSQL")
    assert result is not None
    assert result.startswith("~")


def test_extract_none():
    assert extract_temporal("The API uses JWT tokens") is None


def test_attach_to_facts():
    facts = [
        Fact(subject="api", relation="migrated_to", object="v2"),
        Fact(subject="api", relation="uses", object="jwt"),
    ]
    attach_temporal_to_facts("In April 2024, the API migrated to v2", facts)
    assert facts[0].temporal is not None
    assert facts[1].temporal is not None


def test_attach_no_temporal():
    facts = [Fact(subject="api", relation="uses", object="jwt")]
    attach_temporal_to_facts("The API uses JWT tokens", facts)
    assert facts[0].temporal is None


def test_preserves_existing_temporal():
    facts = [Fact(subject="api", relation="uses", object="jwt", temporal="2024-01")]
    attach_temporal_to_facts("Changed yesterday", facts)
    assert facts[0].temporal == "2024-01"
