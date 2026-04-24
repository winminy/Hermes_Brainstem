from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from plugins.memory.hermes_memory.config.layer import ConfigLayer

from .. import OptionalDependencyError


class LocalEmbeddingBackend:
    def __init__(self, *, config: ConfigLayer, model: object | None = None) -> None:
        self._config = config
        self._model = model

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = self._build_model()
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        local_settings = self._config.settings.embedding.local
        encoded = self.model.encode(
            list(texts),
            batch_size=local_settings.batch_size,
            convert_to_numpy=False,
            normalize_embeddings=local_settings.normalize,
        )
        return [_coerce_vector(vector) for vector in encoded]

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0]

    def _build_model(self) -> Any:
        local_settings = self._config.settings.embedding.local
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise OptionalDependencyError(
                'sentence-transformers is not installed for embedding backend=local. '
                'Install it or switch embedding.backend=api, then run hermes-memory-doctor.'
            ) from exc
        return SentenceTransformer(
            local_settings.model_name,
            device=local_settings.device,
            local_files_only=local_settings.local_files_only,
        )


def _coerce_vector(raw: object) -> list[float]:
    if isinstance(raw, Sequence):
        return [float(value) for value in raw]
    if hasattr(raw, 'tolist'):
        values = raw.tolist()
        if isinstance(values, Sequence):
            return [float(value) for value in values]
    raise ValueError('local embedding output is not sequence-like')
