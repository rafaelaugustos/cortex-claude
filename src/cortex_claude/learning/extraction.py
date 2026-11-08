from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from cortex_claude.core.privacy import strip_private


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(re.findall(r"[a-z0-9_]+", "".join(c for c in plain if not unicodedata.combining(c))))


# Bilingual vocabulary for the zero-model prompt path. Unrecognized concepts
# keep their tokens; cortex_learn supplies retrieval cues for complex lessons.
_GROUPS = (
    "function functions funcao funcoes method methods metodo metodos",
    "small short smaller concise compact pequena pequenas pequeno pequenos curta curtas curto curtos concisa conciso objetiva objetivas objetivo objetivos direta diretas direto diretos succinct brief",
    "large long detailed detalhada detalhadas detalhado detalhados longa longas longo longos",
    "response responses answer answers resposta respostas",
    "test tests testing teste testes testar",
    "code coding codigo programar programming implement implementation implementar implementa implemente endpoint refactor refactoring refatorar refatora refatore",
    "write writing escrever escreva escreve redigir draft texto text email document documento",
    "database databases banco bancos dados sql",
    "deploy deployment release publicar publicacao lancamento",
    "interface interfaces ui frontend front layout tela telas pagina paginas design",
    "prefer prefers preference prefiro prefere preferencia",
    "always sempre", "never nunca", "not nao",
    "english ingles", "portuguese portugues",
    "architecture architectural arquitetura arquitetural arquiteturais",
    "explain explanation explicar explique explicacao explicacoes explanations",
    "debug debugging depurar depuracao bug bugs erro erros error errors",
)
_ALIASES = {word: group.split()[0] for group in _GROUPS for word in group.split()}
_STOP = set("a an the of to for and or with in on is are i we you my me do does please use using eu nos voce meu minha de da do das dos em no na nos nas para por com e o os as um uma quero por favor utilizar usa use usar gosto que mais less menos very muito really realmente prefiro prefer always sempre".split())


def terms(text: str) -> set[str]:
    return {_ALIASES.get(w, w) for w in normalize(text).split() if w not in _STOP and len(w) > 1}


@dataclass
class Observation:
    content: str
    key: str
    applicability: str = "personal"
    triggers: str = ""
    explicit: bool = False
    correction: bool = False
    conditions: dict[str, list[str]] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    max_age_days: int | None = None


def topic(content: str) -> tuple[str, str]:
    words = terms(content)
    if "function" in words and words & {"small", "large"}:
        return "code.function-size", "code function"
    if "response" in words and words & {"small", "large"}:
        return "communication.detail", "*"
    if words & {"portuguese", "english"} and words & {"response", "responda", "responder", "fale", "speak", "reply"}:
        return "communication.language", "*"
    if words & {"pytest", "vitest", "jest"}:
        return "workflow.test-framework", "code test"
    signature = " ".join(sorted(words))
    return "preference." + hashlib.sha256(signature.encode()).hexdigest()[:16], signature


def extract_observations(prompt: str) -> list[Observation]:
    """Learn direct preferences, never quoted/tool text. Complex lessons use
    cortex_learn, interpreted by the assistant already working on the task.
    """
    text = strip_private(prompt)
    text = re.sub(r"<pasted_content\b[^>]*>.*?(?:</pasted_content>|$)", "", text, flags=re.S | re.I)
    text = re.sub(r"```.*?(?:```|$)", "", text, flags=re.S)
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith((">", '"', "'")))
    observations = []
    for sentence in re.split(r"[\n.!?]+", text):
        sentence = sentence.strip(" -\t")
        if not 8 <= len(sentence) <= 400:
            continue
        plain = normalize(sentence)
        if not re.match(r"(?:(?:agora|na verdade|actually|now) )?(?:(?:eu )?(?:prefiro|gosto de|nao gosto de)|i (?:prefer|like|dislike)|(?:sempre|nunca|always|never)\b|(?:de agora em diante|from now on)\b)", plain):
            continue
        contextual = bool(re.search(r"\b(?:neste|nesse|este|esse|this) (?:projeto|servico|arquivo|project|service|file)\b|\b(?:so aqui|only here)\b", plain))
        # Preserve conditional preferences as separate rules. Their topic is
        # derived from the conclusion, so an exception never erases a default.
        # Complex/ambiguous conditions require the working assistant to
        # interpret them; never turn them into an unconditional preference.
        if re.search(r"\b(?:unless|except|exceto|a menos|somente|only|if|se)\b", plain):
            continue
        parts = re.split(r"\b(?:quando|when|ao discutir|ao explicar)\b", sentence, maxsplit=1, flags=re.I)
        conclusion = parts[0].strip(" ,")
        condition_words = (terms(parts[1]) - {"discuss", "discussing", "discutir", "discutimos", "falamos", "sobre", "about", "explain", "explaining"}) if len(parts) == 2 else set()
        if len(parts) == 2 and (not condition_words or condition_words & {"not", "never", "if", "when", "quando", "se"}):
            continue
        conditions = {"all": [" ".join(sorted(condition_words))]} if condition_words else {}
        key, triggers = topic(conclusion)
        observations.append(Observation(
            content=conclusion, key=key,
            applicability="context" if contextual else "personal",
            triggers=triggers,
            explicit=bool(re.search(r"\b(?:sempre|nunca|always|never|de agora em diante|from now on)\b", plain)),
            correction=bool(re.match(r"(?:agora|na verdade|actually|now|de agora em diante|from now on)\b", plain)),
            conditions=conditions,
        ))
    return observations[:5]
