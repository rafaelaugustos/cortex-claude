from __future__ import annotations

import spacy
from spacy.tokens import Token

from cortex_claude.facts.normalizer import normalize_entity, normalize_relation
from cortex_claude.models.fact import Fact

_models: dict[str, spacy.Language] = {}

LANG_MODELS = {
    "en": "en_core_web_sm",
    "pt": "pt_core_news_sm",
    "es": "es_core_news_sm",
    "de": "de_core_news_sm",
    "fr": "fr_core_news_sm",
}


def _get_nlp(lang: str = "en") -> spacy.Language:
    if lang not in _models:
        model_name = LANG_MODELS.get(lang, LANG_MODELS["en"])
        try:
            _models[lang] = spacy.load(model_name)
        except OSError:
            if lang != "en":
                _models[lang] = _get_nlp("en")
            else:
                raise
    return _models[lang]


def _detect_lang(text: str) -> str:
    markers = {
        "pt": [" usa ", " com ", " para ", " tem ", " via ", " como ",
               " não ", " pelo ", " pela ", " dos ", " das ", " que "],
        "es": [" con ", " para ", " tiene ", " por ", " del ", " las ",
               " los ", " una ", " está ", " como ", " pero "],
        "de": [" und ", " der ", " die ", " das ", " ist ", " ein ",
               " eine ", " für ", " mit ", " auf ", " nicht "],
        "fr": [" les ", " des ", " une ", " est ", " pour ", " dans ",
               " avec ", " pas ", " sur ", " qui ", " cette "],
    }
    text_lower = f" {text.lower()} "
    scores = {}
    for lang, words in markers.items():
        scores[lang] = sum(1 for m in words if m in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "en"


def _get_compound_span(token: Token) -> str:
    compounds = sorted(
        [child for child in token.children if child.dep_ in ("compound", "amod", "flat", "flat:name")],
        key=lambda t: t.i,
    )
    parts = [c.text for c in compounds] + [token.text]
    return " ".join(parts)


def extract_facts_spacy(text: str) -> list[Fact]:
    lang = _detect_lang(text)
    nlp = _get_nlp(lang)
    doc = nlp(text)
    facts: list[Fact] = []

    for sent in doc.sents:
        root = sent.root

        if root.pos_ not in ("VERB", "AUX"):
            continue

        subjects = [
            child for child in root.children
            if child.dep_ in ("nsubj", "nsubj:pass", "nsubjpass")
        ]

        objects = [
            child for child in root.children
            if child.dep_ in ("dobj", "obj", "attr", "oprd", "obl")
        ]

        for child in root.children:
            if child.dep_ in ("prep", "case", "obl"):
                for grandchild in child.children:
                    if grandchild.dep_ in ("pobj", "nmod", "obl"):
                        objects.append(grandchild)

        for subj in subjects:
            subj_text = _get_compound_span(subj)
            for obj in objects:
                obj_text = _get_compound_span(obj)

                if len(subj_text.strip()) < 2 or len(obj_text.strip()) < 2:
                    continue

                facts.append(Fact(
                    subject=normalize_entity(subj_text),
                    relation=normalize_relation(root.lemma_),
                    object=normalize_entity(obj_text),
                    confidence=0.8,
                ))

    facts.extend(_extract_ner_facts(doc))
    return facts


def _extract_ner_facts(doc: spacy.tokens.Doc) -> list[Fact]:
    facts: list[Fact] = []

    for ent in doc.ents:
        if ent.label_ in ("CARDINAL", "QUANTITY", "TIME", "PERCENT", "MONEY"):
            head = ent.root.head
            if head.pos_ in ("NOUN", "PROPN"):
                facts.append(Fact(
                    subject=normalize_entity(head.text),
                    relation="has_value",
                    object=ent.text,
                    confidence=0.7,
                ))

    return facts
