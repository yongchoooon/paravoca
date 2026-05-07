from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings

LEGACY_HASH_DIMENSION = 128


class EmbeddingProvider(Protocol):
    name: str
    model: str

    @property
    def dimension(self) -> int:
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


@dataclass
class LegacyHashEmbeddingProvider:
    model: str = "legacy_hash_128"
    name: str = "legacy_hash"

    @property
    def dimension(self) -> int:
        return LEGACY_HASH_DIMENSION

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_legacy_hash_embedding(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return _legacy_hash_embedding(text)


class LocalSentenceTransformerEmbeddingProvider:
    name = "local"

    def __init__(
        self,
        *,
        model: str,
        device: str,
        batch_size: int,
    ) -> None:
        self.model = model
        self.device = device
        self.batch_size = batch_size
        self._model_instance = None

    @property
    def dimension(self) -> int:
        model = self._load_model()
        dimension_getter = getattr(model, "get_embedding_dimension", None) or getattr(
            model,
            "get_sentence_embedding_dimension",
            None,
        )
        dimension = dimension_getter() if dimension_getter else None
        if not dimension:
            probe = self.embed_query("dimension probe")
            return len(probe)
        return int(dimension)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]

    def _load_model(self):
        if self._model_instance is not None:
            return self._model_instance
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError(
                "sentence-transformers is required for EMBEDDING_PROVIDER=local. "
                'Install backend dependencies with `python -m pip install -e ".[dev]"`.'
            ) from exc

        try:
            self._model_instance = SentenceTransformer(self.model, device=self.device)
        except Exception as exc:
            raise RuntimeError(
                "Failed to load local embedding model "
                f"{self.model!r} on device {self.device!r}: {exc}"
            ) from exc
        return self._model_instance

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        try:
            encoded = model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to embed {len(texts)} text(s) with local model {self.model!r}: {exc}"
            ) from exc
        if hasattr(encoded, "tolist"):
            vectors = encoded.tolist()
        else:
            vectors = encoded
        return [[float(value) for value in vector] for vector in vectors]


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    return _get_embedding_provider(
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_device,
        settings.embedding_batch_size,
    )


def clear_embedding_provider_cache() -> None:
    _get_embedding_provider.cache_clear()


@lru_cache
def _get_embedding_provider(
    provider_name: str,
    model: str,
    device: str,
    batch_size: int,
) -> EmbeddingProvider:
    provider = provider_name.strip().lower()
    if provider == "legacy_hash":
        return LegacyHashEmbeddingProvider()
    if provider == "local":
        return LocalSentenceTransformerEmbeddingProvider(
            model=model,
            device=device,
            batch_size=batch_size,
        )
    raise ValueError(
        f"Unsupported EMBEDDING_PROVIDER={provider_name!r}. "
        "Supported providers: legacy_hash, local."
    )


def _legacy_hash_embedding(text: str) -> list[float]:
    vector = [0.0] * LEGACY_HASH_DIMENSION
    tokens = [token for token in text.lower().replace("\n", " ").split(" ") if token]
    if not tokens:
        tokens = ["empty"]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % LEGACY_HASH_DIMENSION
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]
