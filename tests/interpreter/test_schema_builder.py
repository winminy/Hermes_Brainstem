from __future__ import annotations

import json

from jsonschema import validate

from plugins.memory.hermes_memory.backends.llm import OpenAIJSONSchemaLLM, StructuredLLMRequest
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.config.settings import LLMSettings, OpenAISettings
from plugins.memory.hermes_memory.interpreter.schema_builder import SchemaBuilder


class FakeResponsesClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.kwargs: dict[str, object] | None = None
        self.responses = self

    def create(self, **kwargs: object) -> object:
        self.kwargs = dict(kwargs)
        return type('Response', (), {'output_text': json.dumps(self.payload)})()


def test_schema_builder_and_openai_mock_output_validate() -> None:
    settings = HermesMemorySettings(llm=LLMSettings(openai=OpenAISettings(model='gpt-test')))
    config = ConfigLayer.from_settings(settings)
    builder = SchemaBuilder(config)
    schema = builder.build_entry_schema()
    payload: dict[str, object] = {
        'title': '사용자 메모',
        'body': '# 사용자 메모\n\n## Notion properties\n- 유형: 말투',
        'frontmatter': {
            'uuid': 'obs:20260423T1200',
            'area': 'knowledge',
            'type': 'preference',
            'tags': ['사용자정보'],
            'date': '2026-04-23',
            'updated': '2026-04-23',
            'source': ['notion:user-1'],
            'source_type': 'notion',
            'file_type': 'md',
        },
    }
    validate(instance=payload, schema=schema)

    client = FakeResponsesClient(payload)
    backend = OpenAIJSONSchemaLLM(config=config, client=client)
    result = backend.generate(
        StructuredLLMRequest(
            system_prompt='system',
            user_prompt='user',
            output_schema=schema,
        )
    )

    validate(instance=result, schema=schema)
    assert client.kwargs is not None
    assert client.kwargs['model'] == 'gpt-test'
