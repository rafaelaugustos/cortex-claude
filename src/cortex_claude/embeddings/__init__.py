from cortex_claude.embeddings.tokenizer import count_tokens

__all__ = ["EmbeddingEngine", "MODELS", "count_tokens", "get_model_dim"]


def __getattr__(name):
    if name in {"EmbeddingEngine", "MODELS", "get_model_dim"}:
        from cortex_claude.embeddings import engine
        return getattr(engine, name)
    raise AttributeError(name)
