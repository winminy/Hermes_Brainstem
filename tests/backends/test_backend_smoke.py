from __future__ import annotations

from plugins.memory.hermes_memory.backends.embedding import build_embedding_backend
from plugins.memory.hermes_memory.backends.gdrive_mcp import SubprocessGDriveMCPBackend
from plugins.memory.hermes_memory.backends.lightrag import LightRAGHTTPBackend
from plugins.memory.hermes_memory.backends.llm import AnthropicToolUseLLM, OpenAIJSONSchemaLLM
from plugins.memory.hermes_memory.backends.notion import NotionBackend
from plugins.memory.hermes_memory.backends.obsidian_writer import ObsidianWriter
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings


class DummyEmbeddingClient:
    class _Embeddings:
        def create(self, *, input: list[str], model: str, dimensions: int | None) -> object:
            return type('Response', (), {'data': [type('Item', (), {'embedding': [0.1, 0.2]})() for _ in input]})()

    embeddings = _Embeddings()


def test_backend_import_smoke() -> None:
    config = ConfigLayer.from_settings(HermesMemorySettings())

    assert isinstance(NotionBackend(config=config, client=object()), NotionBackend)
    assert isinstance(ObsidianWriter(config=config), ObsidianWriter)
    assert isinstance(OpenAIJSONSchemaLLM(config=config, client=object()), OpenAIJSONSchemaLLM)
    assert isinstance(AnthropicToolUseLLM(config=config, client=object()), AnthropicToolUseLLM)
    assert isinstance(SubprocessGDriveMCPBackend(config=config, command=['true']), SubprocessGDriveMCPBackend)
    assert isinstance(build_embedding_backend(config, api_client=DummyEmbeddingClient()), object)
    assert isinstance(LightRAGHTTPBackend(config=config, embedding_backend=build_embedding_backend(config, api_client=DummyEmbeddingClient())), LightRAGHTTPBackend)
