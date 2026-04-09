from cortex_claude.embeddings.tokenizer import count_tokens


def test_count_tokens_basic():
    assert count_tokens("hello world") > 0


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_count_tokens_longer_text():
    short = count_tokens("hello")
    long = count_tokens("hello world, this is a longer sentence with more tokens")
    assert long > short
