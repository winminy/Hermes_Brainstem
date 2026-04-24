from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from plugins.memory.hermes_memory.config.layer import ConfigLayer

from .api import APIEmbeddingBackend
from .local import LocalEmbeddingBackend


class EmbeddingBackend(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


def build_embedding_backend(
    config: ConfigLayer,
    *,
    api_client: object | None = None,
    local_model: object | None = None,
) -> EmbeddingBackend:
    backend_name = config.settings.embedding.backend
    if backend_name == 'api':
        return APIEmbeddingBackend(config=config, client=api_client)
    if backend_name == 'local':
        return LocalEmbeddingBackend(config=config, model=local_model)
    raise ValueError(f'unsupported embedding backend: {backend_name}')


__all__ = ['EmbeddingBackend', 'APIEmbeddingBackend', 'LocalEmbeddingBackend', 'build_embedding_backend']
