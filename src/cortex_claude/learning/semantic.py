"""Resident local embeddings. Hooks only talk to the daemon, never load ML."""
from __future__ import annotations

import json
import math
import re
import socket
import threading
from collections import OrderedDict
from pathlib import Path

from cortex_claude.core.privacy import strip_private
from cortex_claude.learning.config import LearningConfig
from cortex_claude.learning.extraction import normalize, terms


def valid_vector(value: object) -> bool:
    return (isinstance(value, list) and 32 <= len(value) <= 4096
            and all(type(n) in (float, int) and math.isfinite(n) for n in value))


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    norm = math.sqrt(sum(x*x for x in a) * sum(y*y for y in b))
    return sum(x*y for x, y in zip(a, b)) / norm if norm else 0.0


def compatible(a: str, b: str) -> bool:
    """Similarity is not entailment. Refuse obvious conflicting meanings."""
    left, right = terms(a), terms(b)
    negative = {"not", "never", "dislike", "avoid", "evite", "evitar", "without", "sem", "cannot"}
    def negated(text: str, words: set[str]) -> bool:
        return bool(words & negative) or bool(re.search(r"\b(?:don|doesn|isn|shouldn|wouldn|can|won)[’']t\b", text.casefold()))
    if negated(a, left) != negated(b, right):
        return False
    for positive, opposite in (
        ({"small"}, {"large"}), ({"english"}, {"portuguese"}),
        ({"enable", "enabled", "ativar"}, {"disable", "disabled", "desativar"}),
        ({"before", "antes"}, {"after", "depois"}),
    ):
        if (left & positive and right & opposite) or (right & positive and left & opposite):
            return False
    if re.findall(r"\d+(?:\.\d+)*", a) != re.findall(r"\d+(?:\.\d+)*", b):
        return False
    # Exact technical identifiers are not interchangeable synonyms.
    anchors = {"pytest", "vitest", "jest", "mysql", "postgresql", "sqlite", "redis", "react", "vue", "angular", "python", "javascript", "typescript"}
    if left & anchors != right & anchors:
        return False
    if len(left & anchors) > 1:
        if [w for w in normalize(a).split() if w in anchors] != [w for w in normalize(b).split() if w in anchors]:
            return False
    return set(re.findall(r"`([^`]+)`", a)) == set(re.findall(r"`([^`]+)`", b))


class SemanticClient:
    def __init__(self, home: Path, config: LearningConfig):
        self.home, self.config = home, config
        self.cache: dict[str, list[float]] = {}
        self.unavailable = False

    def vectors(self, texts: list[str]) -> dict[str, list[float]]:
        if not self.config.semantic_enabled or self.unavailable:
            return self.cache
        missing = list(dict.fromkeys(t for t in texts if t and t not in self.cache))[:32]
        if not missing:
            return self.cache
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.config.semantic_timeout_ms / 1000)
                sock.connect(str(self.home / "cortex.sock"))
                sock.sendall(json.dumps({"action": "learning_vectors", "texts": [strip_private(t)[:4000] for t in missing], "model": self.config.semantic_model}).encode())
                sock.shutdown(socket.SHUT_WR)
                data = bytearray()
                while chunk := sock.recv(65536):
                    data.extend(chunk)
                    if len(data) > 1_000_000:
                        raise ValueError("Semantic response too large")
            result = json.loads(data)
            vectors = result.get("vectors", [])
            if result.get("model") != self.config.semantic_model or len(vectors) != len(missing):
                raise ValueError("Semantic backend not ready")
            for text, vector in zip(missing, vectors):
                if not valid_vector(vector):
                    raise ValueError("Invalid semantic vector")
                self.cache[text] = vector
        except (OSError, ValueError, KeyError, TypeError):
            self.unavailable = True  # One bounded attempt per hook/tool call.
        return self.cache


class SemanticService:
    def __init__(self, config: LearningConfig):
        self.config = config
        self.model = None
        self.status = "disabled" if not config.semantic_enabled else "loading"
        self.lock = threading.Lock()
        self.cache: OrderedDict[str, list[float]] = OrderedDict()

    def prepare(self, download: bool = False) -> bool:
        if not self.config.semantic_enabled:
            return False
        try:
            from sentence_transformers import SentenceTransformer
            from huggingface_hub import snapshot_download
            model_path = self.config.semantic_model
            if not Path(model_path).is_dir():
                # Load a concrete snapshot directory. Some transformers
                # versions probe remote processor metadata even with a cached
                # model name; a local path keeps daemon startup fully offline.
                model_path = snapshot_download(model_path, local_files_only=not download,
                    allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"], max_workers=2)
            with self.lock:
                self.model = SentenceTransformer(model_path, local_files_only=True, device="cpu")
                self.model.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False)
            self.status = "ready"
            return True
        except Exception as error:
            self.status = f"unavailable: {type(error).__name__}; run cortex-claude learning prepare"
            return False

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self.status != "ready" or self.model is None:
            return []
        if len(texts) > 32 or any(not isinstance(t, str) or len(t) > 4000 for t in texts):
            raise ValueError("At most 32 texts of 4000 characters")
        with self.lock:
            missing = list(dict.fromkeys(t for t in texts if t not in self.cache))
            if missing:
                vectors = self.model.encode(missing, normalize_embeddings=True, show_progress_bar=False, batch_size=32)
                for text, vector in zip(missing, vectors):
                    self.cache[text] = vector.tolist()
            result = [self.cache[t] for t in texts]
            for text in texts:
                self.cache.move_to_end(text)
            while len(self.cache) > 256:
                self.cache.popitem(last=False)
            return result

    def backfill(self, home: Path) -> None:
        from cortex_claude.learning.store import LearningStore
        with LearningStore(home) as store:
            rows = store.conn.execute(
                "SELECT l.id,l.content FROM lessons l LEFT JOIN lesson_vectors v ON v.lesson_id=l.id AND v.model=? "
                "WHERE v.lesson_id IS NULL AND l.state!='superseded' LIMIT 32", (self.config.semantic_model,),
            ).fetchall()
            vectors = self.encode([r["content"] for r in rows])
            with store.conn:
                for row, vector in zip(rows, vectors):
                    store.conn.execute(
                        "INSERT OR REPLACE INTO lesson_vectors SELECT id,?,? FROM lessons WHERE id=? AND content=?",
                        (self.config.semantic_model, json.dumps(vector), row["id"], row["content"]),
                    )
