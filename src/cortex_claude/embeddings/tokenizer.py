from __future__ import annotations

import tiktoken

_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Estimate token count using OpenAI's cl100k_base encoding.

    This is an approximation, not the real Claude tokenizer — no public
    Claude tokenizer is available to Python code outside Anthropic's API.
    cl100k_base is close enough for budgeting decisions (recall depth,
    dedup, sufficiency thresholds) but the absolute numbers this function
    returns, and anything derived from them (e.g. benchmark token counts,
    `max_tokens` budgets), should be read as directionally correct rather
    than exact Claude token counts.
    """
    return len(_encoder.encode(text))
