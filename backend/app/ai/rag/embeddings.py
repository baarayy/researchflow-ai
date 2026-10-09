"""Embedding model factory.

`HashingEmbeddings` is a deterministic, offline stand-in for demo mode and tests. It uses the
hashing trick on word tokens, so texts that share words get similar vectors and retrieval
behaves sensibly; it has no real semantic understanding.
"""

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings

from app.core.config import Settings

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "which",
        "who",
        "why",
        "will",
        "with",
    ]
)


def _stem(word: str) -> str:
    """Crude suffix stripping so 'licensing', 'licenses' and 'license' share a token."""
    for suffix in ("ing", "es", "ed", "s", "e"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


class HashingEmbeddings(Embeddings):
    def __init__(self, dim: int):
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in tokenize(text):
            h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            vec[h % self.dim] += 1.0 if (h >> 32) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def build_embeddings(settings: Settings) -> Embeddings:
    if settings.embedding_provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        assert settings.openai_api_key is not None  # guaranteed by Settings validation
        return OpenAIEmbeddings(
            model=settings.embedding_model,
            dimensions=settings.embedding_dim,
            api_key=settings.openai_api_key,  # type: ignore[call-arg]  # pydantic alias
            max_retries=settings.external_max_retries,
            request_timeout=settings.llm_timeout_seconds,
        )
    return HashingEmbeddings(settings.embedding_dim)
