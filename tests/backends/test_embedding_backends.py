from __future__ import annotations

import pytest

from plugins.memory.hermes_memory.backends import OptionalDependencyError
from plugins.memory.hermes_memory.backends.embedding import APIEmbeddingBackend, LocalEmbeddingBackend, build_embedding_backend
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.config.settings import EmbeddingSettings


class _EmbeddingDatum:
    def __init__(self, embedding: list[float]) -> None:
        self.embedding = embedding


class FakeEmbeddingAPIClient:
    class _Embeddings:
        def create(self, *, input: list[str], model: str, dimensions: int | None) -> object:
            assert model == 'text-embedding-3-small'
            assert dimensions is None
            vectors = {
                'alpha': [1.0, 2.0],
                'beta': [3.0, 4.0],
            }
            return type('Response', (), {'data': [_EmbeddingDatum(vectors[item]) for item in input]})()

    embeddings = _Embeddings()


class FakeSentenceTransformer:
    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
    ) -> list[list[float]]:
        assert batch_size == 32
        assert convert_to_numpy is False
        assert normalize_embeddings is False
        vectors = {
            'hello': [0.1, 0.2],
            'world': [0.3, 0.4],
        }
        return [vectors[item] for item in texts]


class ImportErrorLocalBackend(LocalEmbeddingBackend):
    def _build_model(self) -> object:
        raise OptionalDependencyError('sentence-transformers is not installed. Run hermes-memory-doctor.')


def test_api_embedding_backend_uses_injected_client() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings())
    backend = APIEmbeddingBackend(config=config, client=FakeEmbeddingAPIClient())

    assert backend.embed_documents(['alpha', 'beta']) == [[1.0, 2.0], [3.0, 4.0]]
    assert backend.embed_query('alpha') == [1.0, 2.0]


def test_local_embedding_backend_uses_injected_model() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings(embedding=EmbeddingSettings(backend='local')))
    backend = LocalEmbeddingBackend(config=config, model=FakeSentenceTransformer())

    assert backend.embed_documents(['hello', 'world']) == [[0.1, 0.2], [0.3, 0.4]]
    assert backend.embed_query('hello') == [0.1, 0.2]


def test_build_embedding_backend_selects_configured_backend() -> None:
    api_config = ConfigLayer.from_settings(HermesMemorySettings())
    local_config = ConfigLayer.from_settings(HermesMemorySettings(embedding=EmbeddingSettings(backend='local')))

    assert isinstance(build_embedding_backend(api_config, api_client=FakeEmbeddingAPIClient()), APIEmbeddingBackend)
    assert isinstance(build_embedding_backend(local_config, local_model=FakeSentenceTransformer()), LocalEmbeddingBackend)


def test_local_embedding_backend_surfaces_doctor_hint() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings(embedding=EmbeddingSettings(backend='local')))
    backend = ImportErrorLocalBackend(config=config)

    with pytest.raises(OptionalDependencyError, match='hermes-memory-doctor'):
        _ = backend.model
