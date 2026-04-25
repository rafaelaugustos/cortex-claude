from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

MODELS = {
    "all-MiniLM-L6-v2": {"dim": 384, "size": "80MB", "speed": "fast", "quality": "good"},
    "all-MiniLM-L12-v2": {"dim": 384, "size": "120MB", "speed": "fast", "quality": "better"},
    "all-mpnet-base-v2": {"dim": 768, "size": "420MB", "speed": "medium", "quality": "high"},
    "BAAI/bge-small-en-v1.5": {"dim": 384, "size": "130MB", "speed": "fast", "quality": "good"},
    "BAAI/bge-base-en-v1.5": {"dim": 768, "size": "440MB", "speed": "medium", "quality": "high"},
    "BAAI/bge-large-en-v1.5": {"dim": 1024, "size": "1.3GB", "speed": "slow", "quality": "excellent"},
    "intfloat/e5-small-v2": {"dim": 384, "size": "130MB", "speed": "fast", "quality": "good"},
    "intfloat/e5-base-v2": {"dim": 768, "size": "440MB", "speed": "medium", "quality": "high"},
    "intfloat/e5-large-v2": {"dim": 1024, "size": "1.3GB", "speed": "slow", "quality": "excellent"},
    "intfloat/multilingual-e5-small": {"dim": 384, "size": "470MB", "speed": "medium", "quality": "good"},
    "intfloat/multilingual-e5-base": {"dim": 768, "size": "1.1GB", "speed": "slow", "quality": "high"},
}

DEFAULT_MODEL = "all-MiniLM-L6-v2"


def get_model_dim(model_name: str) -> int:
    if model_name in MODELS:
        return MODELS[model_name]["dim"]
    return 384


class EmbeddingEngine:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        self._dim: int | None = None

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
            getter = getattr(self._model, 'get_embedding_dimension', None) or self._model.get_sentence_embedding_dimension
            self._dim = getter()
        return self._model

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = get_model_dim(self._model_name)
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, text: str) -> np.ndarray:
        model = self._load()
        return model.encode(text, normalize_embeddings=True)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        return model.encode(texts, normalize_embeddings=True, batch_size=32)

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))
