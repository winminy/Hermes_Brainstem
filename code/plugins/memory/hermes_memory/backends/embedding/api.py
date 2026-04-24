from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from plugins.memory.hermes_memory.config.layer import ConfigLayer

from .. import OptionalDependencyError


class APIEmbeddingBackend:
    def __init__(self, *, config: ConfigLayer, client: object | None = None) -> None:
        self._config = config
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(
            input=list(texts),
            model=self._config.settings.embedding.api.model,
            dimensions=self._config.settings.embedding.api.dimensions,
        )
        return [_coerce_embedding(item.embedding) for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0]

    def _build_client(self) -> Any:
        api_settings = self._config.settings.embedding.api
        api_key = self._config.resolve_secret(
            yaml_value=api_settings.api_key,
            service_name=api_settings.service_name,
            env_vars=api_settings.env_vars,
        )
        if api_key is None:
            raise RuntimeError(
                'Embedding API key is not configured. Set the credential in env, '
                '~/.openclaw/openclaw.json, or yaml, then run hermes-memory-doctor.'
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise OptionalDependencyError(
                'openai is not installed for embedding backend=api. Install it or switch embedding.backend, '
                'then run hermes-memory-doctor.'
            ) from exc
        client_kwargs: dict[str, Any] = {'api_key': api_key, 'timeout': api_settings.timeout_seconds}
        if api_settings.base_url is not None:
            client_kwargs['base_url'] = api_settings.base_url
        return OpenAI(**client_kwargs)


def _coerce_embedding(raw: object) -> list[float]:
    if not isinstance(raw, Sequence):
        raise ValueError('embedding response must be a sequence')
    return [float(value) for value in raw]
