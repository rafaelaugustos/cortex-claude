from cortex_claude.core.privacy import contains_private, is_fully_private, strip_private


def test_strip_private_inline():
    text = "The API key is <private>sk-abc123xyz</private> and it works."
    result = strip_private(text)
    assert "sk-abc123xyz" not in result
    assert "API key" in result


def test_strip_private_multiline():
    text = "Public info.\n<private>\nSECRET_KEY=abc\nDB_PASSWORD=xyz\n</private>\nMore public."
    result = strip_private(text)
    assert "SECRET_KEY" not in result
    assert "DB_PASSWORD" not in result
    assert "Public info" in result
    assert "More public" in result


def test_strip_private_multiple():
    text = "A <private>secret1</private> B <private>secret2</private> C"
    result = strip_private(text)
    assert "secret1" not in result
    assert "secret2" not in result
    assert "A" in result
    assert "B" in result
    assert "C" in result


def test_strip_private_self_closing():
    text = "Before <private/> After"
    result = strip_private(text)
    assert "Before" in result
    assert "After" in result


def test_strip_private_case_insensitive():
    text = "Data <PRIVATE>hidden</PRIVATE> visible"
    result = strip_private(text)
    assert "hidden" not in result
    assert "visible" in result


def test_contains_private():
    assert contains_private("Has <private>secret</private> here") is True
    assert contains_private("No secrets here") is False


def test_is_fully_private():
    assert is_fully_private("<private>all secret</private>") is True
    assert is_fully_private("public <private>secret</private>") is False
    assert is_fully_private("no tags at all") is False


def test_strip_private_no_tags():
    text = "Normal text without any tags"
    assert strip_private(text) == text
