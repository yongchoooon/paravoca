from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings


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
                "sentence-transformers is required for local semantic embedding. "
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
        settings.embedding_model,
        settings.embedding_device,
        settings.embedding_batch_size,
    )


def clear_embedding_provider_cache() -> None:
    _get_embedding_provider.cache_clear()


@lru_cache
def _get_embedding_provider(
    model: str,
    device: str,
    batch_size: int,
) -> EmbeddingProvider:
    return LocalSentenceTransformerEmbeddingProvider(
        model=model,
        device=device,
        batch_size=batch_size,
    )
