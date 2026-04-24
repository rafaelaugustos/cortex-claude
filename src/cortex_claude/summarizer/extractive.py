from __future__ import annotations

import spacy

from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.summarizer.scoring import entity_density_score, position_score, tfidf_scores

_models: dict[str, spacy.Language] = {}

LANG_MODELS = {
    "en": "en_core_web_sm",
    "pt": "pt_core_news_sm",
}


def _detect_lang(text: str) -> str:
    pt_markers = [
        " usa ", " com ", " para ", " tem ", " via ", " como ",
        " não ", " pelo ", " pela ", " dos ", " das ", " que ",
        " são ", " está ", " uma ", " um ",
    ]
    text_lower = f" {text.lower()} "
    pt_count = sum(1 for m in pt_markers if m in text_lower)
    return "pt" if pt_count >= 2 else "en"


def _get_nlp(lang: str = "en") -> spacy.Language:
    if lang not in _models:
        model_name = LANG_MODELS.get(lang, LANG_MODELS["en"])
        try:
            _models[lang] = spacy.load(model_name)
        except OSError:
            _models[lang] = spacy.load(LANG_MODELS["en"])
    return _models[lang]


def summarize(content: str, target_ratio: float = 0.25) -> str:
    lang = _detect_lang(content)
    nlp = _get_nlp(lang)
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
