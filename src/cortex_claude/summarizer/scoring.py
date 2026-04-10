from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


def position_score(index: int, total: int) -> float:
    if index == 0:
        return 0.3
    if index == total - 1:
        return 0.15
    return 0.05


def entity_density_score(sent) -> float:
    ent_count = len(sent.ents)
    return min(ent_count * 0.15, 0.5)


def tfidf_scores(sentences: list[str]) -> np.ndarray:
    if len(sentences) < 2:
        return np.ones(len(sentences))

    vectorizer = TfidfVectorizer(stop_words="english")
    try:
        matrix = vectorizer.fit_transform(sentences)
    except ValueError:
        return np.ones(len(sentences))

    return np.asarray(matrix.sum(axis=1)).flatten()
