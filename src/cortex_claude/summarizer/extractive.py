from __future__ import annotations

import spacy

from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.summarizer.scoring import entity_density_score, position_score, tfidf_scores

_nlp: spacy.Language | None = None


def _get_nlp() -> spacy.Language:
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def summarize(content: str, target_ratio: float = 0.25) -> str:
    nlp = _get_nlp()
    doc = nlp(content)
    sentences = list(doc.sents)

    if len(sentences) <= 2:
        return content

    sentence_texts = [sent.text.strip() for sent in sentences]
    tfidf = tfidf_scores(sentence_texts)

    if tfidf.max() > 0:
        tfidf = tfidf / tfidf.max()

    scored: list[tuple[int, str, float]] = []
    for i, sent in enumerate(sentences):
        score = (
            position_score(i, len(sentences))
            + entity_density_score(sent)
            + float(tfidf[i]) * 0.3
        )
        scored.append((i, sent.text.strip(), score))

    target_tokens = max(int(count_tokens(content) * target_ratio), 10)
    scored.sort(key=lambda x: x[2], reverse=True)

    selected: list[tuple[int, str]] = []
    used_tokens = 0
    for idx, text, _ in scored:
        tokens = count_tokens(text)
        if used_tokens + tokens <= target_tokens:
            selected.append((idx, text))
            used_tokens += tokens

    if not selected:
        selected.append((scored[0][0], scored[0][1]))

    selected.sort(key=lambda x: x[0])
    return " ".join(text for _, text in selected)
